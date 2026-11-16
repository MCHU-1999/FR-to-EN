// Renders a pipeline JSON document (build/<slug>/render.<lang>.json) with the breezy layout.
// Compile with:  typst compile typst/doc.typ out.pdf --root . --font-path fonts --input data=/build/<slug>/render.en.json

#import "breezy.typ": breezy

#let d = json(sys.inputs.at("data"))
#let ui = d.ui
#let accent = rgb(sys.inputs.at("accent", default: "#7AA43E"))
#let ink = accent.darken(40%)
#let headingFont = ("Montserrat", "Liberation Sans")

// ---------------------------------------------------------------- inline runs
#let inline(runs) = {
  for r in runs {
    if r.at("br", default: false) {
      linebreak()
    } else {
      // Zero-width spaces after "_" / "." let identifiers like gcms_date_destruction wrap.
      let body = if r.at("code", default: false) {
        raw(r.t.replace("_", "_\u{200B}").replace(".", ".\u{200B}"))
      } else { [#r.t] }
      if r.at("i", default: false) { body = emph(body) }
      if r.at("b", default: false) { body = strong(body) }
      if r.at("u", default: false) { body = underline(body) }
      let href = r.at("href", default: none)
      if href != none {
        body = if href.starts-with("#") { link(label(href.slice(1)), body) } else { link(href, body) }
      }
      body
    }
  }
}

#let plain-len(runs) = runs.map(r => r.at("t", default: "").len()).sum(default: 0)

// ---------------------------------------------------------------- blocks
#let render-block(b) = {
  let t = b.type
  if t == "para" {
    par(inline(b.runs))
  } else if t == "list" {
    list(..b.items.map(inline))
  } else if t == "meta" {
    block(
      width: 100%,
      inset: (x: 8pt, y: 6pt),
      stroke: (left: 2pt + accent),
      fill: accent.lighten(94%),
      grid(
        columns: (auto, 1fr),
        column-gutter: 1em,
        row-gutter: 0.6em,
        ..b.items.map(it => (text(font: headingFont, size: 8.5pt, fill: ink, weight: "semibold", it.label), inline(it.runs))).flatten(),
      ),
    )
  } else if t == "article" {
    let blocks = b.blocks
    if blocks.len() == 1 and blocks.first().type == "para" and plain-len(blocks.first().runs) < 400 {
      // Short article: run-in label.
      par[#text(font: headingFont, size: 9pt, fill: ink, weight: "semibold")[#b.label:] #h(0.3em) #inline(blocks.first().runs)]
    } else {
      block(sticky: true, above: 1.3em, below: 0.6em,
        text(font: headingFont, size: 10pt, fill: ink, weight: "semibold", b.label))
      for c in blocks { render-block(c) }
    }
  } else if t == "table" {
    let ncols = calc.max(b.header.len(), ..b.rows.map(r => r.len()))
    let columns = if b.at("widths", default: none) != none {
      b.widths.map(w => w * 1fr)
    } else { ncols }
    let cells = b.rows.map(r => {
      let row = r.map(inline)
      row + ((none,) * (ncols - row.len()))
    }).flatten()
    let tbl = table(
      columns: columns,
      ..if b.header.len() > 0 { (table.header(..b.header.map(inline)),) },
      ..cells,
    )
    if b.caption.len() > 0 {
      figure(tbl, caption: inline(b.caption))
    } else {
      block(above: 1em, below: 1em, tbl)
    }
  } else if t == "figure" {
    let img = if b.src == none {
      block(width: 60%, height: 3cm, stroke: 0.5pt + red, align(center + horizon, text(fill: red)[missing image: #b.ref]))
    } else {
      layout(size => {
        let im = image(b.src)
        let w = measure(im).width
        if w > size.width * 0.85 { image(b.src, width: 85%) } else { im }
      })
    }
    if b.caption.len() > 0 {
      figure(img, caption: inline(b.caption))
    } else {
      align(center, block(above: 1em, below: 1em, img))
    }
  }
}

// ---------------------------------------------------------------- document
#show: breezy.with(
  series: d.series,
  code: ui.code,
  subtitle: ui.subtitle,
  title: d.title,
  source: link(d.source_url, d.source_url.split("?").first()),
  author: ui.author,
  date-label: ui.date_label,
  source-label: ui.source_label,
  lang: d.lang,
  accent-colour: accent,
)

#for s in d.sections {
  [#heading(level: s.level, s.heading) #label(s.label)]
  for b in s.blocks { render-block(b) }
}
