# WordprocessingML schema (ISO/IEC 29500-4:2016)

`ISO-IEC29500-4_2016/wml.xsd` is the Task 9 validation gate referenced in
`docs/decisions.md` (C3): output writer tests parse a produced `word/document.xml`
and assert `XMLSchema.validate()` passes.

`wml.xsd` imports `../mce/mc.xsd` by relative path, so the two directories
(`ISO-IEC29500-4_2016/`, `mce/`) must stay siblings exactly as laid out here.

Before validating a real document part, strip the `mc:Ignorable` attribute from
the root element first -- the schema has no attribute declaration for it, so an
unmodified `word/document.xml` fails to validate even when it is well-formed
Markup-Compatibility-conformant OOXML. This is the same workaround the
docx-editing skill's own validator uses; do not treat that failure as a real
schema violation.

```python
from lxml import etree

MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
root = etree.fromstring(xml_bytes)
root.attrib.pop(f"{{{MC_NS}}}Ignorable", None)
schema = etree.XMLSchema(etree.parse("tests/schemas/ISO-IEC29500-4_2016/wml.xsd"))
assert schema.validate(etree.ElementTree(root))
```
