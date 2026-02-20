#!/usr/bin/env python3
"""Pack an unpacked directory back into a .docx, preserving the original ZIP structure."""
import sys, os, zipfile

def pack(unpacked_dir, output_path):
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for root, dirs, files in os.walk(unpacked_dir):
            for f in files:
                full = os.path.join(root, f)
                arcname = os.path.relpath(full, unpacked_dir)
                zout.write(full, arcname)
    print(f"Packed {unpacked_dir} -> {output_path}")

if __name__ == '__main__':
    pack(sys.argv[1], sys.argv[2])
