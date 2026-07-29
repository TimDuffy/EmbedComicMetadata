"""
A python class to encapsulate the ComicBookInfo data
"""

"""
Copyright 2012-2014  Anthony Beville

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import json
from datetime import datetime
from zipfile import ZipFile
from calibre.utils.localization import calibre_langcode_to_name, canonicalize_lang, lang_as_iso639_1
from calibre.utils.unrar import comment
from calibre_plugins.EmbedComicMetadata.metadata.ComicMetadata import ComicMetadata

import sys

if sys.version_info[0] > 2:
    unicode = str


class ComicbookinfoMetadata(ComicMetadata):
    def convert_from_native(self):
        # helper func
        # If item is not in CBI, return None
        def xlate(cbi_entry):
            if cbi_entry in self.native:
                return self.native[cbi_entry]
            else:
                return None

        self.series = xlate('series')
        self.title = xlate('title')
        self.issue = xlate('issue')
        self.publisher = xlate('publisher')
        self.month = xlate('publicationMonth')
        self.year = xlate('publicationYear')
        self.issueCount = xlate('numberOfIssues')
        self.comments = xlate('comments')
        self.credits = xlate('credits')
        self.genre = xlate('genre')
        self.volume = xlate('volume')
        self.volumeCount = xlate('numberOfVolumes')
        self.language = xlate('language')
        self.country = xlate('country')
        self.criticalRating = xlate('rating')
        self.tags = xlate('tags')

        # make sure credits and tags are at least empty lists and not None
        if self.credits is None:
            self.credits = []
        if self.tags is None:
            self.tags = []

        # need to massage the language string to be ISO
        # modified to use a calibre function
        if self.language is not None:
            self.language = lang_as_iso639_1(self.language)

        self.isEmpty = False

    def convert_to_native(self):
        self.native = dict()

        def assign(cbi_entry, md_entry):
            if md_entry is not None:
                self.native[cbi_entry] = md_entry

        def toInt(s):
            i = None
            if type(s) in [str, unicode, int]:
                try:
                    i = int(s)
                except ValueError:
                    pass
            return i

        assign('series', self.series)
        assign('title', self.title)
        assign('issue', self.issue)
        assign('publisher', self.publisher)
        assign('publicationMonth', toInt(self.month))
        assign('publicationYear', toInt(self.year))
        assign('numberOfIssues', toInt(self.issueCount))
        assign('comments', self.comments)
        assign('genre', self.genre)
        assign('volume', toInt(self.volume))
        assign('numberOfVolumes', toInt(self.volumeCount))
        assign('language', calibre_langcode_to_name(canonicalize_lang(self.language)))
        assign('country', self.country)
        assign('rating', self.criticalRating)
        assign('credits', self.credits)
        assign('tags', self.tags)

    def read_from_source(self):
        metadata_string = self.read_from_cbz() if self.book.is_zippy else self.read_from_cbr()
        self.native = self.get_validated_json(metadata_string)

    def write_to_source(self):
        zf = ZipFile(self.book.file, 'a')
        zf.comment = self.get_string_from_native()
        zf._didModify = True
        zf.close()
        self.book.file_dirty = True

    def remove(self):
        zf = ZipFile(self.book.file, 'a')

        # Remove the metadata from the comment
        cbi_string = ''
        zf.comment = cbi_string.encode("utf-8")
        zf._didModify = True
        zf.close()
        self.book.file_dirty = True

    def read_from_cbz(self):
        with ZipFile(self.book.file) as zf:
            return zf.comment
    
    def read_from_cbr(self):
        return comment(self.book.file)
    
    def get_string_from_native(self):
        cbi_container = {'appID': 'ComicTagger/',
                         'lastModified': str(datetime.now()),
                         'ComicBookInfo/1.0': self.native}
        metadata_string = json.dumps(cbi_container)
        return metadata_string.encode("utf-8")

    def get_validated_json(self, metadata_string):
        try:
            cbi_container = json.loads(unicode(metadata_string, 'utf-8'))
            return cbi_container['ComicBookInfo/1.0']
        except:
            return None
