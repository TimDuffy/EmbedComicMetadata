from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2015, dloraine'
__docformat__ = 'restructuredtext en'

import io
import json
import os
import pathlib
import re
import sys
import unicodedata
from zipfile import ZipFile

from calibre.ptempfile import TemporaryFile, TemporaryDirectory
from calibre.utils.magick import Image
from calibre.utils.unrar import extract, comment
from calibre.utils.zipfile import safe_replace
from calibre_plugins.EmbedComicMetadata.config import prefs
from calibre_plugins.EmbedComicMetadata.metadata.CalibreMetadata import CalibreMetadata
from calibre_plugins.EmbedComicMetadata.metadata.ComicinfoXMLMetadata import ComicinfoXMLMetadata
from calibre_plugins.EmbedComicMetadata.metadata.ComicbookinfoMetadata import ComicbookinfoMetadata


python3 = sys.version_info[0] > 2

# image file extensions
IMG_EXTENSIONS = ["jpg", "png", "jpeg", "gif", "bmp", "tiff", "tif", "webp",
                  "svg", "bpg", "psd"]


class Comicbook:
    '''
    An object for calibre to interact with comic metadata.
    '''

    def __init__(self, book_id, ia):
        # initialize the attributes
        self.book_id = book_id
        self.ia = ia
        self.db = ia.gui.current_db.new_api
        self.calibre_metadata = CalibreMetadata(self)
        self.cix_metadata = ComicinfoXMLMetadata(self)
        self.cbi_metadata = ComicbookinfoMetadata(self)
        self._file = None
        self.file_dirty = False
        self.is_zippy = False

        self.calibre_metadata.read()

        # get the comic formats
        if self.db.has_format(book_id, "cbz"):
            self.format = "cbz"
            self.is_zippy = True
        elif self.db.has_format(book_id, "zip"):
            self.format = "zip"
            self.is_zippy = True
        elif self.db.has_format(book_id, "cbr"):
            self.format = "cbr"
        elif self.db.has_format(book_id, "rar"):
            self.format = "rar"
        else:
            self.format = None

        # generate a string with the books info, to show in the completion dialog
        self.info = "{} - {}".format(self.calibre_metadata.native.title, self.calibre_metadata.native.authors[0])
        if self.calibre_metadata.native.series:
            self.info = "{}: {} - ".format(self.calibre_metadata.native.series, self.calibre_metadata.native.series_index) + self.info

    @property
    def file(self):
        if not self._file and self.is_zippy:
            self._file = self.db.format(self.book_id, self.format, as_path=True)
        return self._file
    
    def cleanup(self):
        if self.file_dirty:
            self.db.add_format(self.book_id, self.format, self._file)
        delete_temp_file(self._file)

    def convert_to_cbz(self):
        if self.format == "cbz":
            return False
        elif self.format == "cbr" or (self.format == "rar" and prefs['convert_archives']):
            self.convert_cbr_to_cbz()
            if prefs['delete_cbr']:
                self.db.remove_formats({self.book_id: {"cbr", "rar"}})
            return True
        elif self.format == "zip" and prefs['convert_archives']:
            self.convert_zip_to_cbz()
            if prefs['delete_cbr']:
                self.db.remove_formats({self.book_id: {"zip"}})
            return True
        return False
    
    def add_dir_to_zip(self, zf, tdir, arcname):
        import os
        for dirpath, dirs, files in os.walk(tdir):
            for f in files:
                fn = os.path.join(dirpath, f)
                zf.write(fn, f'{arcname}/{f}')

    def convert_cbr_to_cbz(self):
        '''
        Converts a rar or cbr-comic to a cbz-comic
        '''
        with TemporaryDirectory('_cbr2cbz') as tdir:
            # extract the rar file
            ffile = self.db.format(self.book_id, self.format, as_path=True)
            extract(ffile, tdir)
            comments = comment(ffile)
            delete_temp_file(ffile)

            # make the cbz file
            with TemporaryFile("comic.cbz") as tf:
                zf = ZipFile(tf, "w")
                self.add_dir_to_zip(zf, tdir, clean_title(self.calibre_metadata.title))
                if comments:
                    zf.comment = comments.encode("utf-8")
                zf.close()
                # add the cbz format to calibres library
                self.db.add_format(self.book_id, "cbz", tf)
                self.format = "cbz"
                
            if prefs['clean_cbz']:
                self.clean_cbz()

    def convert_zip_to_cbz(self):
        zf = self.db.format(self.book_id, "zip", as_path=True)
        new_fname = os.path.splitext(zf)[0] + ".cbz"
        os.rename(zf, new_fname)
        self.db.add_format(self.book_id, "cbz", new_fname)
        delete_temp_file(new_fname)
        self.format = "cbz"
        
        if prefs['clean_cbz']:
            self.clean_cbz()
            
    # CBZ mark
    def stringFromMetadata(self, metadata):
        cbi_container = self.createJSONDictionary(metadata)
        return json.dumps(cbi_container)
    
    
    def is_cbi_valid(self):
        # Ensure metadata is set
        self.overlay_metadata()

        # Generate what the string should be
        cbi_string = self.cbi_metadata.get_string_from_native()
        if not python3:
            cbi_string = cbi_string.decode('utf-8', 'ignore')

        # ensure we have a temp file
        self.make_temp_cbz_file()

        # Read current cbi comment
        zf = ZipFile(self.file, "r")
        curr_str = zf.comment
        zf.close()

        return cbi_string == curr_str

    def is_cbi_empty(self):
       # ensure we have a temp file
        self.make_temp_cbz_file()

        # Read current cbi comment
        zf = ZipFile(self.file, "r")
        curr_str = zf.comment
        zf.close()

        return curr_str == None or curr_str == "".encode("utf-8")

    def is_cix_valid(self):
        # Ensure metadata is set
        self.overlay_metadata()

        # Generate what the string should be
        cix_string = self.cix_metadata.get_metadata_string()

        # ensure we have a temp file
        self.make_temp_cbz_file()

        # Read current xml file
        zf = ZipFile(self.file, "r")
        curr_file = zf.open('ComicInfo.xml', 'r')
        curr_str = io.TextIOWrapper(curr_file).read()
        curr_file.close()

        # count current # of pages
        pages = 0
        for name in zf.namelist():
            if name.lower().rpartition('.')[-1] in IMG_EXTENSIONS:
                pages += 1
        zf.close()

        if self.comic_metadata.pageCount != pages:
            return False

        return cix_string == curr_str

    def is_cbz_dirty(self):
        '''
        Determines if a CBZ file has a dirty/unwanted file structure
        '''
        ffile = self.db.format(self.book_id, self.format, as_path=True)
        tmpf = ZipFile(ffile)
        filename_list = tmpf.namelist()

        # A 'dirty' zip has one (or more) of these cases:
        #   Case 1: Metadata is not clean
        #       a. There are duplicate files
        #       b. ComicInfo.xml does not exist at <root_dir>/ComicInfo.xml
        #       c. ComicInfo.xml content is not up to date
        #       d. ComicBookInfo comment is not up to date
        #   Case 2: Directory structure is up to date
        #       a. file name matches <root_dir>/<book_name>/*
        #       b. filename does not contain invalid extension
        #       c. filename does not match scanner tag
        #       d. filename does not match embedded cover

        # Case 1a
        if len(set(filename_list)) < len(filename_list):
            return True
        # Case 1b
        if 'ComicInfo.xml' not in filename_list:
            return True
        else:
            # Case 1c
            if not self.is_cix_valid():
                return True
        # Case 1d
        if not self.is_cbi_empty():
            return True

        for f in filename_list:
            # We already checked ComicInfo.xml, so ignore it here
            if f == 'ComicInfo.xml':
                continue
            # Case 2a
            if os.path.dirname(f) != clean_title(self.calibre_metadata.title):
                return True
            # Case 2b
            if pathlib.Path(f).suffix in [".xhtml", ".html", ".css", ".xml", ".sfv"]:
                return True
            # Case 2c+d
            if os.path.basename(f).__contains__('zz'):
                return True
            # Case 2c+d
            if os.path.basename(f) in ['cover.jpeg', 'cover.jpeg', 'page.jpg', 'zSoU-Nerd.jpg']:
                return True

        return False

    def action_mark_cbz(self):
        should_mark = True if self.format in ["cbr", "zip"] else self.is_cbz_dirty()
        if should_mark:
            self.ia.gui.current_db.data.add_marked_ids({self.book_id: 'shit_files_m8'})

        return should_mark

    # CBZ cleanup
    def clean_cbz(self):
        '''
        cleans directory structure for a cbz comic
        '''

        # Shortcut for files that are already cleaned
        should_clean = self.is_cbz_dirty()
        if not should_clean:
            return False

        with TemporaryDirectory('_extractedfiles') as tdir:
            # extract the zip file
            ffile = self.db.format(self.book_id, self.format, as_path=True)
            tmpf = ZipFile(ffile)
            tmpf.extractall(tdir)
            comments = tmpf.comment
            delete_temp_file(ffile)
            tmpf.close()

            # Gather file paths from extracted zip
            all_files = []
            for root, _, files in os.walk(tdir):
                for f in files:
                    all_files.append(os.path.abspath(os.path.join(root, f)))

            # clean up dir structure
            with TemporaryDirectory('_cleancbz') as cleandir:
                with TemporaryFile("comic.cbz") as tf:
                    zf = ZipFile(tf, "w")

                    for f in all_files:
                        # Skip non-image files
                        if pathlib.Path(f).suffix in [".xhtml", ".html", ".css", ".xml", ".sfv"]:
                            continue
                        # Remove scanner tags
                        if os.path.basename(f).__contains__('zz'):
                            continue
                        # Remove embedded covers and scanner tags
                        if os.path.basename(f) in ['cover.jpg', 'cover.jpeg', 'page.jpg', 'zSoU-Nerd.jpg']:
                            continue
                        else:
                            zf.write(f, f'{clean_title(self.calibre_metadata.title)}/{os.path.basename(f)}')

                    if comments:
                        zf.comment = "".encode("utf-8")

                    self.overlay_metadata()
                    if prefs['cix_embed']:
                        cix_string = self.cix_metadata.get_metadata_string()
                        zf.writestr("ComicInfo.xml", cix_string)

                    zf.close()

                    # add the cbz format to calibres library
                    self.db.add_format(self.book_id, "cbz", tf)
                    self.format = "cbz"

                    delete_temp_file(tf)
            self.file = self.db.format(self.book_id, "cbz", as_path=True)

            return True

    def update_cover(self):
        # get the calibre cover
        cover_path = self.db.cover(self.book_id, as_path=True)
        fmt = cover_path.rpartition('.')[-1]
        new_cover_name = "00000000_cover." + fmt

        # search for a previously embeded cover
        zf = ZipFile(self.file)
        cover_info = None
        for name in zf.namelist():
            if name.rsplit(".", 1)[0] == "00000000_cover":
                cover_info = name
                break
        zf.close()

        if cover_info:
            with open(self.file, 'r+b') as zf, open(cover_path, 'r+b') as cp:
                safe_replace(zf, cover_info, cp)
        else:
            zf = ZipFile(self.file, "a")
            zf.write(cover_path, new_cover_name)
            zf.close()

        self.file_dirty = True
        delete_temp_file(cover_path)

    def count_pages(self):
        zf = ZipFile(self.file)
        pages = 0
        for name in zf.namelist():
            if name.lower().rpartition('.')[-1] in IMG_EXTENSIONS:
                pages += 1
        zf.close()
        return pages

    def get_picture_size(self):
        zf = ZipFile(self.file)
        files = zf.namelist()

        size_x, size_y = 0, 0
        index = 1
        while index < 10 and index < len(files):
            fname = files[index]
            if fname.lower().rpartition('.')[-1] in IMG_EXTENSIONS:
                with zf.open(fname) as ffile:
                    img = Image()
                    try:
                        img.open(ffile)
                        size_x, size_y = img.size
                    except:
                        pass
                if size_x < size_y:
                    break
            index += 1
        zf.close()
        size = round(size_x * size_y / 1000000, 2)
        return size


def delete_temp_file(ffile):
    try:
        import os
        if os.path.exists(ffile):
            os.remove(ffile)
    except:
        pass


def clean_title(s):
    return re.sub(r'[^\w_,\-\.\(\)\s]', '_', strip_accents(s))


def clean_authors(l: list[str]):
    return [a.replace("_no_sync", "") for a in l]


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
