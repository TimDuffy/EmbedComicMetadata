from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2015, dloraine'
__docformat__ = 'restructuredtext en'

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

# the comic rack metadata always lives in the root of the archive
CIX_NAME = "ComicInfo.xml"

# files which are not wanted inside a comic archive
JUNK_EXTENSIONS = [".xhtml", ".html", ".css", ".xml", ".sfv"]
JUNK_FILENAMES = ["cover.jpg", "cover.jpeg", "page.jpg", "zsou-nerd.jpg",
                  "zdcp.jpg"]
SCANNER_TAG = "zz"


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
                self.is_zippy = True

            if prefs['clean_cbz']:
                self.clean_cbz()

    def convert_zip_to_cbz(self):
        zf = self.db.format(self.book_id, "zip", as_path=True)
        new_fname = os.path.splitext(zf)[0] + ".cbz"
        os.rename(zf, new_fname)
        self.db.add_format(self.book_id, "cbz", new_fname)
        delete_temp_file(new_fname)
        self.format = "cbz"
        self.is_zippy = True

        if prefs['clean_cbz']:
            self.clean_cbz()

    # CBZ mark
    def build_cbi_string(self):
        '''
        Builds the ComicBookInfo comment which belongs in this comic: what the
        comment already contains, overlaid with the metadata from calibre.

        Cleaning and the dirty check both go through this, so that they can
        not disagree about what the comment should look like.
        '''
        cbi_metadata = ComicbookinfoMetadata(self)
        cbi_metadata.read()
        cbi_metadata.overlay(self.calibre_metadata)
        cbi_metadata.convert_to_native()

        return cbi_metadata.get_string_from_native()

    def is_cbi_valid(self):
        '''
        Determines if the zip comment already holds the metadata we would
        write into it.

        Compares the metadata itself and not the comment string, because the
        string carries a lastModified timestamp which changes on every write.
        '''
        cbi_metadata = ComicbookinfoMetadata(self)
        cbi_metadata.read()
        curr_metadata = cbi_metadata.native
        cbi_metadata.overlay(self.calibre_metadata)
        cbi_metadata.convert_to_native()

        return cbi_metadata.native == curr_metadata

    def is_cbi_empty(self):
       # ensure we have a temp file
        self.make_temp_cbz_file()

        # Read current cbi comment
        zf = ZipFile(self.file, "r")
        curr_str = zf.comment
        zf.close()

        return curr_str == None or curr_str == "".encode("utf-8")

    def build_cix_string(self, pages=None):
        '''
        Builds the ComicInfo.xml which belongs in this comic: what the file
        already contains, overlaid with the metadata from calibre.

        Cleaning and the dirty check both go through this, so that they can
        not disagree about what the metadata should look like.

        :param pages: the page count to use, for when the archive we are
                      building does not exist yet. Defaults to the pages in
                      the current archive.
        '''
        cix_metadata = ComicinfoXMLMetadata(self)
        cix_metadata.read()
        cix_metadata.overlay(self.calibre_metadata)
        cix_metadata.pageCount = self.count_pages() if pages is None else pages
        cix_metadata.convert_to_native()

        return cix_metadata.get_metadata_string()

    def is_cix_valid(self):
        # ensure we have a temp file
        self.make_temp_cbz_file()

        # Read current xml file
        zf = ZipFile(self.file, "r")
        curr_str = zf.read(CIX_NAME).decode("utf-8")
        zf.close()

        return self.build_cix_string() == curr_str

    def is_cbz_dirty(self):
        '''
        Determines if a CBZ file has a dirty/unwanted file structure

        A 'dirty' zip has one (or more) of these cases:
          Case 1: Metadata is not clean
              a. There are duplicate files
              b. ComicInfo.xml does not exist at <root_dir>/ComicInfo.xml
              c. ComicInfo.xml content is not up to date
              d. the ComicBookInfo comment is not up to date

                 Cases b to d follow the embed options: metadata we do not
                 embed should not be in the file at all, otherwise cleaning a
                 comic could never make it clean.
          Case 2: Directory structure is not clean
              a. a file does not match <root_dir>/<book_name>/<file>
              b. a file is not wanted in a comic archive, see is_junk_file
        '''
        zf = ZipFile(self.file)
        filename_list = zf.namelist()
        zf.close()

        # Case 1a
        if len(set(filename_list)) < len(filename_list):
            return True
        # Case 1b + 1c
        if prefs['cix_embed']:
            if CIX_NAME not in filename_list:
                return True
            if not self.is_cix_valid():
                return True
        elif CIX_NAME in filename_list:
            # we do not embed it, so a cleaned comic does not contain it
            return True
        # Case 1d
        if prefs['cbi_embed']:
            if not self.is_cbi_valid():
                return True
        elif not self.is_cbi_empty():
            return True

        comic_dir = clean_title(self.calibre_metadata.title)
        for f in filename_list:
            # the metadata lives in the root, we already checked it above
            if f == CIX_NAME:
                continue
            # Case 2a
            if os.path.dirname(f) != comic_dir:
                return True
            # Case 2b
            if is_junk_file(f):
                return True

        return False

    def action_mark_cbz(self):
        should_mark = True if self.format in ["cbr", "zip"] else self.is_cbz_dirty()
        if should_mark:
            self.ia.gui.current_db.data.add_marked_ids({self.book_id: 'shit_files_m8'})

        return should_mark

    def make_temp_cbz_file(self):
        if not self._file and self.format == "cbz":
            self._file = self.db.format(self.book_id, "cbz", as_path=True)

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

                    comic_dir = clean_title(self.calibre_metadata.title)
                    pages = 0
                    for f in all_files:
                        # drop unwanted files, the metadata is rewritten below
                        if is_junk_file(f):
                            continue
                        zf.write(f, f'{comic_dir}/{os.path.basename(f)}')
                        if f.lower().rpartition('.')[-1] in IMG_EXTENSIONS:
                            pages += 1

                    if prefs['cix_embed'] or prefs['cbi_embed']:
                        # remember the page count of the archive we are
                        # building, so that the metadata we embed below and
                        # the metadata in calibre stay in sync with it
                        self.calibre_metadata.pageCount = pages
                        self.calibre_metadata.write()

                    if prefs['cbi_embed']:
                        zf.comment = self.build_cbi_string()
                    elif comments:
                        # drop metadata we are not supposed to embed
                        zf.comment = "".encode("utf-8")

                    if prefs['cix_embed']:
                        zf.writestr(CIX_NAME, self.build_cix_string(pages))

                    zf.close()

                    # add the cbz format to calibre library
                    self.db.add_format(self.book_id, "cbz", tf)
                    self.format = "cbz"
                    self.is_zippy = True

                    delete_temp_file(tf)
            self._file = self.db.format(self.book_id, "cbz", as_path=True)

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


def is_junk_file(name):
    '''
    Determines if a file does not belong in a cleaned comic archive.

    Both the dirty check and the cleanup use this, otherwise the cleanup can
    leave behind a file which keeps the comic marked as dirty forever.
    '''
    basename = os.path.basename(name)

    # metadata, playlists and the like, ComicInfo.xml gets written seperately
    if pathlib.Path(basename).suffix.lower() in JUNK_EXTENSIONS:
        return True
    # scanner tags
    if SCANNER_TAG in basename:
        return True
    # embedded covers and scanner credits
    return basename.lower() in JUNK_FILENAMES


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
