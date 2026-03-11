# ADR-002: defusedxml for RSS Parsing

- **Date**: 2026-03-11
- **Status**: Accepted

## Context
v3.1 used `xml.etree.ElementTree.fromstring()` to parse RSS/Atom feeds. `ElementTree` is vulnerable to XXE (XML External Entity) injection attacks. A malicious RSS feed could craft an XML payload with an `SYSTEM` entity referencing local files (e.g. `/etc/passwd`), exfiltrating file contents into the parsed tree.

## Decision
Replace all `import xml.etree.ElementTree as ET` with `import defusedxml.ElementTree as ET`. The API is identical — zero other changes required.

## Rationale
- `defusedxml` is the Python security community standard for safe XML parsing
- Drop-in replacement — no refactoring needed
- Disables: entity expansion, external entity loading, DTD retrieval
- Maintained, well-tested, zero performance overhead for our use case

## Consequences
- ✅ XXE attack surface eliminated
- ✅ Zero refactoring cost (identical API)
- ✅ One-line dependency addition
- ⚠️ Adds one runtime dependency

## Alternatives Considered
| Option | Reason Rejected |
|--------|----------------|
| `lxml` with `resolve_entities=False` | Heavier dependency, C extension compilation |
| `feedparser` | Hides the XML layer; less control over field extraction |
| Manual XML sanitisation | Error-prone, not a complete defence |
