"""
A python class to encapsulate ComicRack's ComicInfo.xml data
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

import sys
import xml.etree.ElementTree as ET
from io import StringIO
from zipfile import ZipFile
from calibre.utils.unrar import extract_member, names
from calibre.utils.zipfile import safe_replace
from calibre_plugins.EmbedComicMetadata.metadata.ComicMetadata import ComicMetadata
from calibre_plugins.EmbedComicMetadata.utils import safe_delete, listToString


if sys.version_info[0] > 2:
    python3 = True
    unicode = str


class ComicinfoXMLMetadata(ComicMetadata):

    @property
    def zipinfo(self):
        if not getattr(self, "_zipinfo_read", False):
            zf = ZipFile(self.book.file)
            self._zipinfo = None
            for name in zf.namelist():
                if name.lower() == "comicinfo.xml":
                    self._zipinfo = name
                    break
            zf.close()
            self._zipinfo_read = True
        return self._zipinfo
    
    @zipinfo.setter
    def zipinfo(self, val):
        self._zipinfo = val
        self._zipinfo_read = True

    def indent(self, elem, level=0):
        # for making the XML output readable
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                self.indent(elem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    def convert_to_native(self):
        # build a tree structure
        root = ET.Element("ComicInfo")
        root.attrib['xmlns:xsi'] = "http://www.w3.org/2001/XMLSchema-instance"
        root.attrib['xmlns:xsd'] = "http://www.w3.org/2001/XMLSchema"
        # helper func

        def assign(cix_entry, md_entry):
            if md_entry is not None:
                ET.SubElement(root, cix_entry).text = u"{0}".format(md_entry)

        assign('Title', self.title)
        assign('Series', self.series)
        assign('Number', self.issue)
        assign('Count', self.issueCount)
        assign('Volume', self.volume)
        assign('AlternateSeries', self.alternateSeries)
        assign('AlternateNumber', self.alternateNumber)
        assign('StoryArc', self.storyArc)
        assign('SeriesGroup', self.seriesGroup)
        assign('AlternateCount', self.alternateCount)
        assign('Summary', self.comments)
        assign('Notes', self.notes)
        assign('Year', self.year)
        assign('Month', self.month)
        assign('Day', self.day)

        # add credits
        for role in self.credit_synonyms.keys():
            credit_list = [c['person'] for c in self.credits if c['role'] == role]
            if len(credit_list) > 0:
                node = ET.SubElement(root, role)
                node.text = listToString(credit_list)

        # calibre custom columns like tags return tuples, so we need to handle
        # these specially
        self.characters = tuple_to_string(self.characters)
        self.teams = tuple_to_string(self.teams)
        self.locations = tuple_to_string(self.locations)
        self.genre = tuple_to_string(self.genre)
        self.tags = tuple_to_string(self.tags)

        assign('Publisher', self.publisher)
        assign('Imprint', self.imprint)
        assign('Genre', self.genre)
        if self.tags:
            assign('Tags', self.tags)
        assign('Web', self.webLink)
        assign('PageCount', self.pageCount)
        assign('LanguageISO', self.language)
        assign('Format', self.format)
        assign('AgeRating', self.maturityRating)
        if self.blackAndWhite is not None and self.blackAndWhite:
            ET.SubElement(root, 'BlackAndWhite').text = "Yes"
        assign('Manga', self.manga)
        assign('Characters', self.characters)
        assign('Teams', self.teams)
        assign('Locations', self.locations)
        assign('ScanInformation', self.scanInfo)
        assign('GTIN', self.gtin)

        #  loop and add the page entries under pages node
        if len(self.pages) > 0:
            pages_node = ET.SubElement(root, 'Pages')
            for page_dict in self.pages:
                page_node = ET.SubElement(pages_node, 'Page')
                page_node.attrib = page_dict

        # self pretty-print
        self.indent(root)

        # wrap it in an ElementTree instance, and save as XML
        tree = ET.ElementTree(root)
        self.native = tree

    def convert_from_native(self):
        root = self.native.getroot()

        if root.tag != 'ComicInfo':
            raise 1

        # Helper function
        def xlate(tag):
            node = root.find(tag)
            if node is not None:
                return node.text
            else:
                return None

        self.series = xlate('Series')
        self.title = xlate('Title')
        self.issue = xlate('Number')
        self.issueCount = xlate('Count')
        self.volume = xlate('Volume')
        self.alternateSeries = xlate('AlternateSeries')
        self.alternateNumber = xlate('AlternateNumber')
        self.alternateCount = xlate('AlternateCount')
        self.comments = xlate('Summary')
        self.notes = xlate('Notes')
        self.year = xlate('Year')
        self.month = xlate('Month')
        self.day = xlate('Day')
        self.publisher = xlate('Publisher')
        self.imprint = xlate('Imprint')
        self.genre = xlate('Genre')
        self.webLink = xlate('Web')
        self.language = xlate('LanguageISO')
        self.format = xlate('Format')
        self.manga = xlate('Manga')
        self.characters = xlate('Characters')
        self.teams = xlate('Teams')
        self.locations = xlate('Locations')
        self.pageCount = xlate('PageCount')
        self.scanInfo = xlate('ScanInformation')
        self.storyArc = xlate('StoryArc')
        self.seriesGroup = xlate('SeriesGroup')
        self.maturityRating = xlate('AgeRating')
        self.gtin = xlate('GTIN')

        tmp = xlate('BlackAndWhite')
        self.blackAndWhite = False
        if tmp is not None and tmp.lower() in ["yes", "true", "1"]:
            self.blackAndWhite = True
        # Now extract the credit info
        for n in root:
            if (n.tag == 'Writer' or
                    n.tag == 'Penciller' or
                    n.tag == 'Inker' or
                    n.tag == 'Colorist' or
                    n.tag == 'Letterer' or
                    n.tag == 'Editor' or
                    n.tag == 'CoverArtist'):
                if n.text is not None:
                    for name in n.text.split(','):
                        self.addCredit(name.strip(), n.tag)

        # Tags
        tags = xlate('Tags')
        if tags is not None:
            self.tags = [t for t in tags.split(", ")]

        # parse page data now
        pages_node = root.find("Pages")
        if pages_node is not None:
            for page in pages_node:
                self.pages.append(page.attrib)
                # print page.attrib

        self.isEmpty = False

    def read_from_source(self):
        metadata_string = self.read_from_cbz() if self.book.is_zippy else self.read_from_cbr()
        if not metadata_string:
            self.native = None
            return
        self.native = ET.ElementTree(ET.fromstring(metadata_string))

    def write_to_source(self):
        header = '<?xml version="1.0"?>\n'
        metadata_string = header + ET.tostring(self.native.getroot(), "unicode") if python3 else header + ET.tostring(self.native.getroot())

        if not python3:
            metadata_string = metadata_string.decode('utf-8', 'ignore')
        # use the safe_replace function from calibre to prevent coruption
        if self.zipinfo is not None:
            with open(self.book.file, 'r+b') as zf:
                safe_replace(zf, self.zipinfo, StringIO(metadata_string))
        # save the metadata in the file
        else:
            zf = ZipFile(self.book.file, "a")
            zf.writestr("ComicInfo.xml", metadata_string)
            zf.close()
        self.book.file_dirty = True

    def remove(self):
        # Remove ComicInfo.xml from the file
        if self.zipinfo is None:
            return
        with open(self.book.file, 'r+b') as zf:
            safe_delete(zf, self.zipinfo)
        self.book.file_dirty = True

    def read_from_cbz(self):
        with ZipFile(self.book.file) as zf:
            for name in zf.namelist():
                if name.lower() == "comicinfo.xml":
                    self.zipinfo = name
                    return zf.read(name)
    
    def read_from_cbr(self):
        with open(self.book.file, 'rb') as stream:
            # get the cix metadata
            fnames = list(names(stream))
            for name in fnames:
                if name.lower() == "comicinfo.xml":
                    return extract_member(stream, match=None, name=name)[1]


def tuple_to_string(metadata):
    if metadata and not (isinstance(metadata, str) or isinstance(metadata, unicode)):
        string = ""
        for item in metadata:
            if len(string) > 0:
                string += ", "
            string += item
        return string
    return metadata
