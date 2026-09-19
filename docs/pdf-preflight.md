# PDF preflight

Inspect an existing PDF without modifying it or rebuilding its publication:

```console
nix run .#mathpub -- preflight path/to/student.pdf --json
nix run .#mathpub -- preflight path/to/student.pdf --profile print-policy.toml --json
```

The command works outside a MathPub project as well. Without a profile it reports
measurements only: a successful command does **not** mean a PDF is print-ready.
With a profile, violations and unresolved requested checks return exit code 3.
The complete report is retained in `error.details.report` on policy failure;
successful JSON output uses the usual `data` envelope. Inputs are never modified.

## Library-owned policies

For example (illustrative values, **not** any printer's requirements):

```toml
schema = 1
id = "my-paperback-v1"
width_pt = 432
height_pt = 648
page_count = 120
tolerance_pt = 0.01
require_embedded_fonts = true
min_font_pt = 8
min_stroke_pt = 0.5
```

Only `schema` and `id` are required. Omit rules you do not want enforced. Width
and height must be supplied together. Unknown keys, negative thresholds, and
non-finite values are rejected. All units are PDF points (1/72 inch), not TeX
points. Page numbers are one-based **physical pages**, not printed folios.
Increment the policy ID when changing library requirements; reports also include
the entire effective policy, PDF SHA-256, byte count, and tool versions.

Trim measurements use TrimBox (falling back to CropBox per PDF semantics), account
for UserUnit and page rotation, and check every page. All five page boxes are
reported, including their nonzero origins. Embedded-font checks inspect fonts
used in text operations, including descendant fonts, rather than requiring every
unused resource to be embedded. This checks embedding presence, not font validity
or license rights. Type 3 content is flagged as unresolved.

Type size is the text em height after text/graphics transforms, not a glyph's
visible ink height. Form XObjects are traversed with their resources, transforms,
and inherited graphics state. Stroke measurements give conservative lower/upper
width bounds under affine transforms, including shear. If the requested minimum
falls between those bounds the result is `unresolved`, not a fabricated precise
measurement. A zero-width device hairline fails a positive width requirement.
All configured size/trim comparisons use `tolerance_pt` (default 0.01).

## Report and extension API

`mathpub.preflight.inspect_pdf(Path(...))` returns reusable measurements.
`preflight_pdf(path, profile_dict)` returns those measurements plus findings and
`passed`; policy failures do not raise in this API. Invalid PDFs/policies raise
`MathpubError`. Each check carries its rule, physical page, expected/measured
values, and status: `pass`, `fail`, `unresolved`, or `not-applicable`. A page with
no text/strokes has no applicable font/stroke measurements; it is **not** thereby
approved as an intentional blank. Libraries may add semantic rules to these
reports without embedding book titles, chapter phrases, or fixed trims in MathPub.

## Current limits

Optional Poppler-backed checks are now available:

```toml
text_safe_margin_pt = [36, 36, 36, 36] # left, top, right, bottom of displayed CropBox
allowed_blank_pages = [2] # omitting this rule disables blank-page checks
require_grayscale = true
raster_dpi = 150
ink_threshold = 250 # any channel below this is ink
color_tolerance = 2 # maximum RGB channel difference
[[content_expectations]]
id = "chapter-heading"
page = 3
text = "Chapter One"
count = 1
```

Text bounds use Poppler word boxes in the displayed CropBox coordinate system,
with top-left origin. Content expectations can check folios and library-specific
headings/counts without built-in book phrases. Raster checks detect graphics-only
pages, not just extractable text. They run only when requested and record DPI,
ink/color pixel counts. Grayscale pixels are not PDF color-space certification;
word boxes do not establish artwork safety. These tools do not certify print
acceptance or exact semantic relationships between nearby words.

Annotation appearances, patterns, soft masks, stroked text, Type 3 glyph drawing, and transforms
changed within a path are reported as unsupported; requested font/stroke policies
fail closed on such pages. Clipping/optional visibility and outlined text are not
interpreted; measurements may include invisible/clipped drawing instructions.
Encrypted, malformed, or excessively nested forms are rejected. These checks do
not prove artwork safety, PDF/X compliance, retailer acceptance, or editorial
approval. No rasterization, retailer connection, or upload occurs.
