"""
One-time remediation: Synthea (this JVM/Windows combo) wrote NDJSON files using the
platform default charset (Windows-1252) instead of UTF-8 whenever a line contained an
accented character (Hispanic-heritage names from Synthea's demographic modules). FHIR/JSON
requires UTF-8, so these lines are technically malformed JSON -- DuckDB's JSON reader
correctly refuses to parse them.

This script finds every .ndjson file under synthea/output/**/fhir/, and for any file that
isn't valid UTF-8, re-encodes it: per line, try UTF-8 first (already-valid lines pass through
unchanged byte-for-byte), and for lines that fail, decode as cp1252 (the mis-encoding source)
and re-encode as UTF-8. Writes to a temp file in the same directory and atomically replaces
the original via os.replace, so a crash mid-write never leaves a half-fixed file.

This is a byte-level re-encoding fix (recovering the correct characters), not a data change.
"""
import codecs
import glob
import os
import sys

ROOT = "C:/dev/fhirsql/synthea/output"


def is_valid_utf8(path, chunk_size=8 * 1024 * 1024):
    decoder = codecs.getincrementaldecoder("utf-8")()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError:
                return False
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def fix_file(path):
    tmp_path = path + ".fixtmp"
    fixed_lines = 0
    total_lines = 0
    with open(path, "rb") as fin, open(tmp_path, "wb") as fout:
        for raw_line in fin:
            total_lines += 1
            try:
                raw_line.decode("utf-8")
                fout.write(raw_line)
            except UnicodeDecodeError:
                fixed_line = raw_line.decode("cp1252").encode("utf-8")
                fout.write(fixed_line)
                fixed_lines += 1
    os.replace(tmp_path, path)
    return fixed_lines, total_lines


def main():
    files = sorted(glob.glob(f"{ROOT}/*/*/fhir/*.ndjson"))
    print(f"Scanning {len(files)} ndjson files under {ROOT} ...")
    bad = [f for f in files if not is_valid_utf8(f)]
    print(f"{len(bad)} files need remediation.")

    total_fixed_lines = 0
    for i, path in enumerate(bad, 1):
        fixed_lines, total_lines = fix_file(path)
        total_fixed_lines += fixed_lines
        print(f"[{i}/{len(bad)}] {path}: fixed {fixed_lines}/{total_lines} lines")

    print(f"\nDone. {len(bad)} files remediated, {total_fixed_lines} lines re-encoded total.")

    # Verify
    still_bad = [f for f in bad if not is_valid_utf8(f)]
    if still_bad:
        print(f"WARNING: {len(still_bad)} files still invalid after remediation:", still_bad)
        sys.exit(1)
    print("Verification passed: all previously-bad files are now valid UTF-8.")


if __name__ == "__main__":
    main()
