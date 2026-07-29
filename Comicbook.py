from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2015, dloraine'
__docformat__ = 'restructuredtext en'

import os
from zipfile import ZipFile
from calibre.ptempfile import TemporaryFile, TemporaryDirectory
from calibre.utils.magick import Image
from calibre.utils.unrar import extract, comment
from calibre.utils.zipfile import safe_replace
from calibre_plugins.EmbedComicMetadata.config import prefs
from calibre_plugins.EmbedComicMetadata.metadata.CalibreMetadata import CalibreMetadata
from calibre_plugins.EmbedComicMetadata.metadata.ComicinfoXMLMetadata import ComicinfoXMLMetadata
from calibre_plugins.EmbedComicMetadata.metadata.ComicbookinfoMetadata import ComicbookinfoMetadata
from calibre_plugins.EmbedComicMetadata.utils import add_dir_to_zipfile

import sys

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
                add_dir_to_zipfile(zf, tdir)
                if comments:
                    zf.comment = comments.encode("utf-8")
                zf.close()
                # add the cbz format to calibres library
                self.db.add_format(self.book_id, "cbz", tf)
                self.format = "cbz"

    def convert_zip_to_cbz(self):
        zf = self.db.format(self.book_id, "zip", as_path=True)
        new_fname = os.path.splitext(zf)[0] + ".cbz"
        os.rename(zf, new_fname)
        self.db.add_format(self.book_id, "cbz", new_fname)
        delete_temp_file(new_fname)
        self.format = "cbz"

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
