# Canonical envelope serialization

Envelope JSON uses this profile so conforming implementations produce byte-identical output.

1. Encode as UTF-8 without a byte-order mark.
2. Sort object keys lexicographically at every nesting level.
3. Indent nested values with two spaces.
4. Use `\n` line endings.
5. End the file with exactly one trailing newline.
6. Use `": "` between keys and values and `","` between members, with no trailing whitespace.
7. Normalize strings to Unicode NFC and emit Unicode characters literally rather than as `\uXXXX` escapes.
8. Omit optional fields when absent. Use `null` only when a field is present and explicitly empty.
9. Omit empty arrays and objects. Emit booleans and integers as native JSON values.

Decimal source values, including `value_num`, are JSON strings. Preserve the exact source lexeme,
including trailing zeroes and exponent notation. Parsers must not convert those strings through a
binary floating-point type before serialization.

Each `values[]` answer has exactly one question identifier. CAP eCC/eCP answers carry the full
OBX-3.1 identifier as `ecp_code` (for example, `2118.1000043`) and omit `item_num`.
`item_num` is reserved for a verified NAACCR data item number. A CAP code's numeric prefix is
never a NAACCR item number by inference.

For HL7 v2, each OBR group emits one envelope. `source.obr_ordinal` is its
one-based position in the message. Envelopes from the same byte stream repeat
the same `raw.sha256` and are stored in ordinal order beneath one
`intake.inbound_message`. A narrative OBR keeps its own `report_loinc` and
`report.narrative`; a synoptic OBR keeps its own `report_loinc` and answers.

Date precision is `year`, `month`, `day`, `hour`, `minute`, or `second`.
Components below the stated precision are null. An HL7 timezone offset, when
present, is preserved as `±HH:MM` without UTC conversion. Parsing a timestamp
must not fill missing minutes or seconds with zero.

The optional `episode` object carries a source episode identifier and its
optional authority and sequence. Loaders derive the non-null
`naaccr_value.episode_key` in this order:

1. `e:` followed by SHA-256 of NFC-normalized
   `assigning_authority + U+001F + episode_source_value + U+001F + sequence_number`;
   absent authority and sequence use empty strings.
2. Otherwise, `a:` followed by SHA-256 of NFC-normalized `report.accession`.
3. Otherwise, `m:` followed by `raw.sha256`.

Hashes are lowercase hexadecimal. This keeps the key within SQL Server's
100-character column limit and makes identical source identities deterministic.
