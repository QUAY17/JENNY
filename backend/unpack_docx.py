#!/usr/bin/env python3
"""Unpack a .docx to a directory, pretty-printing XML."""
import sys, os, zipfile
import xml.dom.minidom

def unpack(docx_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(docx_path, 'r') as z:
        for name in z.namelist():
            data = z.read(name)
            out_path = os.path.join(out_dir, name)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            if name.endswith('.xml') or name.endswith('.rels'):
                try:
                    pretty = xml.dom.minidom.parseString(data).toprettyxml(indent="  ")
                    lines = [l for l in pretty.split('\n') if l.strip()]
                    text = '\n'.join(lines[1:])  # skip xml declaration from minidom
                    # Re-add proper declaration
                    if '<?xml' in lines[0]:
                        text = lines[0] + '\n' + '\n'.join(lines[1:])
                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.write(text)
                except:
                    with open(out_path, 'wb') as f:
                        f.write(data)
            else:
                with open(out_path, 'wb') as f:
                    f.write(data)
    print(f"Unpacked {docx_path} to {out_dir}")

if __name__ == '__main__':
    unpack(sys.argv[1], sys.argv[2])
