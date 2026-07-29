import os
import shutil
from calibre.ptempfile import SpooledTemporaryFile
from calibre.utils.zipfile import ZipFile as ZFile

# from calibres zipfile utility
def add_dir_to_zipfile(zf, path, prefix=''):
    '''
    Add a directory recursively to the zip file with an optional prefix.
    '''
    if prefix:
        zf.writestr(prefix+'/', b'')
    fp = (prefix + ('/' if prefix else '')).replace('//', '/')
    for f in os.listdir(path):
        arcname = fp + f
        f = os.path.join(path, f)
        if os.path.isdir(f):
            add_dir_to_zipfile(zf, f, prefix=arcname)
        else:
            zf.write(f, arcname)


def safe_delete(zipstream, name):
    '''
    Delete a file in a zip file in a safe manner. This proceeds by extracting
    and re-creating the zipfile. This is necessary because :method:`ZipFile.delete`
    sometimes created corrupted zip files.


    :param zipstream:  Stream from a zip file
    :param name:       The name of the file to delete

    '''

    z = ZFile(zipstream, 'r')

    with SpooledTemporaryFile(max_size=100*1024*1024) as temp:
        ztemp = ZFile(temp, 'a')
        for obj in z.infolist():
            if isinstance(obj.filename, str):
                obj.flag_bits |= 0x16  # Set isUTF-8 bit
            # Write all files to new zipfile except the deleted file
            if obj.filename != name:
                ztemp.writestr(obj, z.read_raw(obj), raw_bytes=True)
        ztemp.close()
        z.close()
        temp.seek(0)
        zipstream.seek(0)
        zipstream.truncate()
        shutil.copyfileobj(temp, zipstream)
        zipstream.flush()

def listToString(l):
    string = ""
    if l is not None:
        for item in l:
            if len(string) > 0:
                string += ", "
            string += item
    return string
