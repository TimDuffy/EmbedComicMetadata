import unicodedata
import sys
from datetime import date
from functools import partial
from calibre.utils.html2text import html2text
from calibre.utils.date import UNDEFINED_DATE
from calibre.utils.localization import lang_as_iso639_1
from calibre.ebooks.metadata import MetaInformation
from calibre.utils.date import parse_only_date
from calibre.ebooks.metadata import author_to_author_sort
from calibre.utils.localization import calibre_langcode_to_name
from calibre_plugins.EmbedComicMetadata.metadata.ComicMetadata import ComicMetadata
from calibre_plugins.EmbedComicMetadata.config import prefs

python3 = sys.version_info[0] > 2

class CalibreMetadata(ComicMetadata):
    def convert_from_native(self):
        mi = self.native

        # update the fields of comic metadata
        self._update_field("title", mi.title)
        self.addCredits("Writer", mi.authors)
        self._update_field("series", mi.series)
        self._update_field("issue", mi.series_index)
        self._update_field("tags", mi.tags)
        self._update_field("publisher", mi.publisher)
        self._update_field("criticalRating", mi.rating)
        # need to check for None
        if mi.comments:
            self._update_field("comments", html2text(mi.comments))
        if mi.language:
            self._update_field("language", lang_as_iso639_1(mi.language))
        if mi.pubdate != UNDEFINED_DATE:
            self._update_field("year", mi.pubdate.year)
            self._update_field("month", mi.pubdate.month)
            self._update_field("day", mi.pubdate.day)

        # check for gtin in identifiers
        if 'gtin' in mi.identifiers:
            self._update_field("gtin", mi.identifiers['gtin'])
        # if no gtin use isbn
        elif 'isbn' in mi.identifiers:
            self._update_field("gtin", mi.identifiers['isbn'])

        # custom columns
        field = partial(self.book.db.field_for, book_id=self.book.book_id)

        # artists
        self.addCredits("Penciller", field(prefs['penciller_column']))
        self.addCredits("Inker", field(prefs['inker_column']))
        self.addCredits("Colorist", field(prefs['colorist_column']))
        self.addCredits("Letterer", field(prefs['letterer_column']))
        self.addCredits("CoverArtist", field(prefs['cover_artist_column']))
        self.addCredits("Editor", field(prefs['editor_column']))
        # others
        self._update_field("storyArc", field(prefs['storyarc_column']))
        self._update_field("characters", field(prefs['characters_column']))
        self._update_field("teams", field(prefs['teams_column']))
        self._update_field("locations", field(prefs['locations_column']))
        self._update_field("volume", field(prefs['volume_column']))
        self._update_field("genre", field(prefs['genre_column']))
        self._update_field("issueCount", field(prefs['count_column']))
        self._update_field("pageCount", field(prefs['pages_column']))
        self._update_field("webLink", get_link(field(prefs['comicvine_column'])))
        self._update_field("manga", field(prefs['manga_column']))
        self._update_field("format", field(prefs['format_column']))
        self._update_field("maturityRating", field(prefs['maturity_column']))

        self.isEmpty = False
    
    def convert_to_native(self):
        # start with a fresh calibre metadata
        self.native = MetaInformation(None, None)
        # shorten some functions
        update_field = partial(update_calibre_field, target=self.native)

        # Get title, if no title, try to assign series infos
        if self.title:
            self.native.title = self.title
        elif self.series:
            self.native.title = self.series
            if self.issue:
                self.native.title += " " + str(self.issue)
        else:
            self.native.title = ""

        # tags
        if self.tags != [] and prefs['import_tags']:
            self.native.tags = self.tags

        # simple metadata
        update_field("authors", self.get_role("Writer"))
        update_field("series", self.series)
        update_field("rating", self.criticalRating)
        update_field("publisher", self.publisher)
        # special cases
        if self.language:
            update_field("language", calibre_langcode_to_name(self.language))
        if self.comments:
            update_field("comments", self.comments.strip())
        # issue
        if self.issue:
            try:
                if not python3 and isinstance(self.issue, unicode):
                    self.native.series_index = unicodedata.numeric(self.issue)
                else:
                    self.native.series_index = float(self.issue)
            except ValueError:
                pass
        # pub date
        puby = self.year
        pubm = self.month
        pubd = self.day
        if puby is not None:
            try:
                dt = date(
                    int(puby),
                    6 if pubm is None else int(pubm),
                    15 if pubd is None else int(pubd)
                )
                dt = parse_only_date(str(dt))
                self.native.pubdate = dt
            except:
                pass
        # gtin
        if self.gtin:
            self.native.set_identifiers({"gtin": self.gtin})
			
        # artists
        self.update_column(prefs['penciller_column'], self.get_role("Penciller"))
        self.update_column(prefs['inker_column'], self.get_role("Inker"))
        self.update_column(prefs['colorist_column'], self.get_role("Colorist"))
        self.update_column(prefs['letterer_column'], self.get_role("Letterer"))
        self.update_column(prefs['cover_artist_column'], self.get_role("CoverArtist"))
        self.update_column(prefs['editor_column'], self.get_role("Editor"))
        # others
        self.update_column(prefs['storyarc_column'], self.storyArc)
        self.update_column(prefs['characters_column'], self.characters)
        self.update_column(prefs['teams_column'], self.teams)
        self.update_column(prefs['locations_column'], self.locations)
        self.update_column(prefs['genre_column'], self.genre)
        ensure_int(self.issueCount, self.update_column, prefs['count_column'], self.issueCount)
        ensure_int(self.volume, self.update_column, prefs['volume_column'], self.volume)
        self.update_column(prefs['pages_column'], self.pageCount)
        self.update_column(prefs['image_size_column'], self.imageSize)
        if self.webLink:
            self.update_column(prefs['comicvine_column'], '<a href="{}">Comic Vine</a>'.format(self.webLink))
        self.update_column(prefs['manga_column'], self.manga)
        self.update_column(prefs['format_column'], self.format)
        self.update_column(prefs['maturity_column'], self.maturityRating)

    def read_from_source(self):
        self.native = self.book.db.get_metadata(self.book.book_id)

    def write_to_source(self):
        self.book.db.set_metadata(self.book.book_id, self.native)

    def remove(self):
        raise NotImplementedError("Calibre metadata can not be removed")

    def overlayTags(self, new_tags):
        if self.tags != [] and not prefs['overwrite_calibre_tags']:
            new_tags = list(set(self.tags + new_tags))
        if len(new_tags) > 0:
            setattr(self, "tags",  new_tags)

    def update_column(self, col_name, value):
        '''
        Updates the given custom column with the name of col_name to value
        '''
        if col_name and value:
            custom_cols = self.book.db.field_metadata.custom_field_metadata()
            col = custom_cols[col_name]
            col['#value#'] = value
            self.native.set_user_metadata(col_name, col)
    
    def addCredits(self, role, persons):
        '''
        Sets all persons with the given role to credits
        '''
        if persons and len(persons) > 0:
            for person in persons:
                self.addCredit(swap_author_names_back(person), role)

    def get_role(self, role):
        '''
        Gets a list of persons with the given role.
        '''
        if prefs['swap_names']:
            return [author_to_author_sort(credit['person']) for credit in self.credits
                    if credit['role'] == role]
        return [credit['person'] for credit in self.credits
                if credit['role'] == role]
                
    def _update_field(self, field, source):
        '''
        Sets the attribute field of target to the value of source
        '''
        if source:
            setattr(self, field, source)


# Helper Functions
# ------------------------------------------------------------------------------

def update_calibre_field(field, source, target):
    '''
    Sets the attribute field of target to the value of source
    '''
    if source:
        target.set(field, source)

def swap_author_names_back(author):
    if author is None:
        return author
    if ',' in author:
        parts = author.split(',')
        if len(parts) <= 1:
            return author
        surname = parts[0]
        return '%s %s' % (' '.join(parts[1:]), surname)
    return author

def get_link(text):
    import re

    if text:
        link = re.findall('<a href="?\'?([^"\'>]*)', text)
        if link:
            return link[0]
    return ""

def ensure_int(value, func, *args):
    try:
        _ = int(value)
        func(*args)
    except (ValueError, TypeError):
        pass
