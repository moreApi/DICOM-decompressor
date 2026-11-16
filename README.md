This is mostly vibed.
# dicom-decompressor

Takes a `DICOMDIR` (the index file found on DICOM CDs, DVDs and USB exports),
decompresses every image it references, and writes each series (image stack)
to its own folder.

Images are converted to uncompressed **Explicit VR Little Endian**. All metadata
is kept; only the pixel data and transfer syntax change. Decompression is done
with [GDCM](https://github.com/malaterre/GDCM) (`python-gdcm`), which handles
JPEG, JPEG-LS, JPEG 2000 and RLE.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.12+ (uv installs it if needed)

## Usage

```bash
uv run dicom-decompressor /path/to/export/DICOMDIR
```

The output folder is created next to the folder that contains the `DICOMDIR`,
named `<folder>_decompressed`:

```
export/
  DICOMDIR
  IMAGES/...
export_decompressed/
  S001_Localizer/
    00001.dcm
    00002.dcm
  S002_T1_MPRAGE/
    00001.dcm
    ...
```

- **One folder per series:** images are grouped by the Series Instance UID in
  each image file, so the order of entries in the `DICOMDIR` doesn't matter.
- **Folder names:** `S<series number>_<series description>`. If both are
  missing, the Series Instance UID is used. If two series would get the same
  name, `_2`, `_3`, ... is appended.
- **File names:** the instance number, zero-padded (`00001.dcm`), so files sort
  in stack order. If an image has no instance number, its original file name is
  kept.
- **Failures:** files that can't be read, decompressed or written (for example
  structured reports or other non-image objects) are logged as warnings and
  skipped. A summary is logged at the end.
- No new `DICOMDIR` is written to the output.

The output location must be writable. If the `DICOMDIR` is on a read-only
medium such as a mounted CD, copy the export to a local disk first.

## Development

```bash
uv sync
```

The code lives in `src/dicom_decompressor/__init__.py`.
