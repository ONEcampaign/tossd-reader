#!/usr/bin/env bash
# Downloads every currently published TOSSD per-year vintage file into a dated
# archive directory, verbatim, alongside its response headers and a
# sha256sums.txt manifest.
#
# This is the manual operator response to a canary drift alert
# (.github/workflows/canary.yml): before refreshing known_vintages.json /
# known_years.json / the packaged snapshot to match a new upstream vintage,
# run this script first to preserve a durable copy of the OUTGOING vintage
# (the one about to be replaced in the publisher's cache).
#
# Usage:
#   scripts/archive_vintage.sh [destination-dir]
#
# destination-dir defaults to ./tossd-archive-<UTC date>. Deliberately dumb:
# bash + curl + shasum only, no other dependencies. Sweeps year 2019 through
# the current UTC calendar year (same range discovery.py's own HEAD sweep
# covers) and simply skips a year that isn't currently published (HTTP 404).

set -euo pipefail

URL_PREFIX="https://tossd.online/tossddata_"
FIRST_YEAR=2019

archive_dir="${1:-./tossd-archive-$(date -u +%F)}"
mkdir -p "$archive_dir"

current_year="$(date -u +%Y)"
today="$(date -u +%F)"

sums_file="$archive_dir/sha256sums.txt"
: > "$sums_file"

for year in $(seq "$FIRST_YEAR" "$current_year"); do
    url="${URL_PREFIX}${year}.parquet"
    payload_file="$archive_dir/tossddata_${year}.parquet"
    headers_file="$archive_dir/tossddata_${year}.headers.txt"

    echo "Fetching ${year}: ${url}"
    http_code="$(curl -sS -D "$headers_file" -o "$payload_file" -w '%{http_code}' "$url" || echo "000")"

    if [ "$http_code" != "200" ]; then
        echo "  -> HTTP ${http_code}; ${year} is not currently published, skipping."
        rm -f "$payload_file" "$headers_file"
        continue
    fi

    (cd "$archive_dir" && shasum -a 256 "tossddata_${year}.parquet" >> "sha256sums.txt")
done

cat > "$archive_dir/README.md" <<EOF
# TOSSD vintage archive — ${today}

This directory was created by \`scripts/archive_vintage.sh\` on ${today} (UTC), as
the manual operator response to a tossd-reader canary drift alert: it archives
every per-year TOSSD file currently published at
\`https://tossd.online/tossddata_<year>.parquet\` (one file per reporting year,
2019 through the current calendar year, skipping any year that 404s) exactly
as downloaded, alongside each file's raw response headers
(\`tossddata_<year>.headers.txt\`) and a \`sha256sums.txt\` manifest, so the
OUTGOING vintage is preserved before the publisher's cache rolls over to a new
one.
EOF

echo "Archive written to $archive_dir"
