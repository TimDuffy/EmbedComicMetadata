from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2015, dloraine'
__docformat__ = 'restructuredtext en'

from calibre.gui2 import error_dialog, info_dialog

from calibre_plugins.EmbedComicMetadata.config import prefs
from calibre_plugins.EmbedComicMetadata.languages.lang import _L
from calibre_plugins.EmbedComicMetadata.Comicbook import Comicbook

import sys

python3 = sys.version_info[0] > 2

def import_to_calibre(ia, action):
    def _import_to_calibre(book):
        if action == "both" or action == "cix":
            book.cix_metadata.read()
            book.calibre_metadata.overlay(book.cix_metadata)
        if action == "both" or action == "cbi":
            book.cbi_metadata.read()
            book.calibre_metadata.overlay(book.cbi_metadata)
        if book.cix_metadata.isEmpty and book.cbi_metadata.isEmpty:
            return False
        if prefs['auto_count_pages']:
            book.calibre_metadata.pageCount = book.count_pages()
        if prefs['get_image_sizes']:
            book.calibre_metadata.imageSize = book.get_picture_size()
        book.calibre_metadata.write()
        return True

    iterate_over_books(ia, _import_to_calibre,
                       _L["Updated Calibre Metadata"],
                       _L['Updated calibre metadata for {} book(s)'],
                       _L['The following books had no metadata: {}'],
                       prefs['convert_reading'])


def embed_into_comic(ia, action):
    def _embed_into_comic(book):
        if not book.is_zippy:
            return False
        if action == "both" or action == "cix":
            book.cix_metadata.read()
            book.cix_metadata.overlay(book.calibre_metadata)
            book.cix_metadata.write()
        if action == "both" or action == "cbi":
            book.cbi_metadata.read()
            book.cbi_metadata.overlay(book.calibre_metadata)
            book.cbi_metadata.write()
        return True

    iterate_over_books(ia, _embed_into_comic,
                       _L["Updated comics"],
                       _L['Updated the metadata in the files of {} comics'],
                       _L['The following books were not updated: {}'])


def convert(ia):
    def _convert_to_cbz(book):
        return book.convert_to_cbz()
    iterate_over_books(ia, _convert_to_cbz,
                       _L["Converted files"],
                       _L['Converted {} book(s) to cbz'],
                       _L['The following books were not converted: {}'],
                       False)


def embed_cover(ia):
    def _embed_cover(book):
        if not book.is_zippy:
            return False
        book.update_cover()
        return True

    iterate_over_books(ia, _embed_cover,
                       _L["Updated Covers"],
                       _L['Embeded {} covers'],
                       _L['The following covers were not embeded: {}'])


def count_pages(ia):
    def _count_pages(book):
        if not book.is_zippy:
            return False
        book.calibre_metadata.pageCount = book.count_pages()
        book.calibre_metadata.write()
        return True

    iterate_over_books(ia, _count_pages,
                       _L["Counted pages"],
                       _L['Counted pages in {} comics'],
                       _L['The following comics were not counted: {}'])


def mark_cbz(ia):
    def _mark_cbz(metadata):
        if metadata.format not in ["cbr", "zip", "cbz"]:
            return False
        return metadata.action_mark_cbz()

    iterate_over_books(ia, _mark_cbz,
                       _L["Marked comics"],
                       _L['Marked the following comics: {}'],
                       _L['{} comics were not marked'],
                       False)


def clean_cbz(ia):
    def _clean_cbz(metadata):
        if metadata.format != "cbz":
            return False
        metadata.action_count_pages()
        return metadata.clean_cbz()

    iterate_over_books(ia, _clean_cbz,
                       _L["Cleaned comics"],
                       _L['Cleaned the following comics: {}'],
                       _L['{} comics were not cleaned'])



def remove_metadata(ia):
    def _remove_metadata(book):
        if not book.is_zippy:
            return False
        book.cix_metadata.remove()
        book.cbi_metadata.remove()
        return True

    iterate_over_books(ia, _remove_metadata,
                        _L["Removed metadata"],
                        _L['Removed metadata in {} comics'],
                        _L['The following comics did not have metadata removed: {}'])


def get_image_size(ia):
    def _get_image_size(book):
        if not book.is_zippy:
            return False
        book.calibre_metadata.imageSize = book.get_picture_size()
        book.calibre_metadata.write()
        return True

    iterate_over_books(ia, _get_image_size,
                       _L["Updated Calibre Metadata"],
                       _L['Updated calibre metadata for {} book(s)'],
                       _L['The following books were not updated: {}'])


def iterate_over_books(ia, func, title, ptext, notptext,
                       should_convert=None,
                       convtext=_L["The following comics were converted to cbz: {}"]):
    '''
    Iterates over all selected books. For each book, it checks if it should be
    converted to cbz and then applies func to the book.
    After all books are processed, gives a completion message.
    '''
    processed = []
    not_processed = []
    converted = []

    if should_convert is None:
        should_convert = prefs["convert_cbr"]

    # iterate through the books
    for book_id in get_selected_books(ia):
        book = Comicbook(book_id, ia)

        # sanity check
        if book.format is None:
            not_processed.append(book.info)
            continue

        if should_convert and book.convert_to_cbz():
            converted.append(book.info)

        if func(book):
            processed.append(book.info)
        else:
            not_processed.append(book.info)

        book.cleanup()

    # show a completion message
    msg = ptext.format(lst2string(processed))
    if should_convert and len(converted) > 0:
        msg += '\n' + convtext.format(lst2string(converted))
    if len(not_processed) > 0:
        msg += '\n' + notptext.format(len(not_processed))
    info_dialog(ia.gui, title, msg, show=True)


def get_selected_books(ia):
    # Get currently selected books
    rows = ia.gui.library_view.selectionModel().selectedRows()
    if not rows or len(rows) == 0:
        return  error_dialog(ia.gui, _L['Cannot update metadata'],
                     _L['No books selected'], show=True)
    # Map the rows to book ids
    return map(ia.gui.library_view.model().id, rows)


def lst2string(lst):
    if len(lst) == 0:
        return "\n    " + "[None]\n    "
    if python3:
        return "\n    " + "\n    ".join(lst)
    return "\n    " + "\n    ".join(item.encode('utf-8') for item in lst)
