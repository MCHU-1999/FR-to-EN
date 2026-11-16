// Vendored from breezy-report 0.1.0 (@preview/breezy-report)
// Original: "breezy-report: A clean colour-customisable engineering report template"
// Author: Breanna Barraclough – https://github.com/brebarra/breezy-report – License: MIT (see LICENSE-breezy-report)
//
// Local changes for FR-to-EN:
// - student/course fields renamed to documentation fields (series, code, subtitle, source…)
// - cover/header labels changed ("Student ID" → "Source", "Submission date" → "Translated"…)
// - fonts: Montserrat (bundled in /fonts) + Libertinus Serif (built into Typst)
// - colour: light accent used for fills/rules; darker `ink` used for text, for contrast
// - outline limited to depth 2; list titles follow `lang`; smaller table text

#let in-body = state("in-body", false)

#let end-breezy() = {
  in-body.update(false)
}

#let breezy(
  series: "Documentation",
  code: "",
  subtitle: "",
  title: "Document title",
  source: "",
  author: "",
  date: datetime.today(),
  date-label: "Translated",
  source-label: "Source",
  lang: "en",
  accent-colour: rgb("#7AA43E"),
  report,
) = [
  #let headingFont = ("Montserrat", "Liberation Sans")
  #let bodyFont = ("Libertinus Serif", "Liberation Serif")
  // `accent-colour` is light: keep it for bars, rules and borders, and use
  // darker shades wherever text sits on white or on the accent.
  #let ink = accent-colour.darken(40%)
  #let on-accent = accent-colour.darken(72%)
  #let i18n = if lang == "fr" {
    (figures: "Liste des figures", tables: "Liste des tableaux", fig: [Fig.], tab: [Tab.])
  } else {
    (figures: "List of Figures", tables: "List of Tables", fig: [Fig.], tab: [Tab.])
  }

  #set document(title: title, author: author)
  #set text(font: bodyFont, size: 10.5pt, lang: lang)
  #set par(leading: 0.7em, spacing: 1.1em, justify: true)

  #show heading: it => block(
    above: 1.5em,
    below: 0.9em,
    sticky: true,
    text(font: headingFont, fill: ink, it),
  )
  #show heading.where(level: 1): set text(size: 16pt)
  #show heading.where(level: 2): set text(size: 13pt)
  #show heading.where(level: 3): set text(size: 11pt)
  #set heading(numbering: "1.")

  #show raw.where(block: true): it => block(
    fill: accent-colour.lighten(90%),
    inset: 12pt,
    radius: 3pt,
    width: 100%,
    text(fill: luma(15%), it),
  )
  // Inline code uses highlight (not box) so long identifiers can wrap in narrow table cells.
  #show raw.where(block: false): it => highlight(
    fill: accent-colour.lighten(85%),
    extent: 1pt,
    radius: 2pt,
    text(size: 0.88em, fill: on-accent, it),
  )

  #set line(length: 100%)

  #set list(marker: (
    text(fill: ink)[•],
    text(fill: ink)[‣],
    text(fill: ink)[–],
  ))

  // Colours all supplements
  #set figure.caption(separator: [ — ])
  #show figure.caption: it => [
    #text(fill: ink, weight: "bold")[#it.supplement #context it.counter.display(it.numbering)]#it.separator#it.body
  ]

  #show ref: it => text(fill: ink, it)
  #show link: it => text(fill: ink, it)

  #show figure.where(kind: image): set figure(supplement: i18n.fig)
  #show figure.where(kind: table): set figure(supplement: i18n.tab)
  #show figure.where(kind: table): set figure.caption(position: top)
  #show figure: set block(breakable: true)

  // Table header: bold white on dark accent; light accent borders.
  #show table.cell.where(y: 0): set text(weight: "bold", font: headingFont, fill: white, size: 8.5pt)
  #show table: set text(size: 9pt)
  #set table(
    stroke: 0.5pt + accent-colour,
    fill: (x, y) => if y == 0 { ink } else if calc.even(y) { accent-colour.lighten(92%) },
    inset: 5pt,
    align: left,
  )
  #show table: set par(justify: false)

  // Page settings
  #set page(
    paper: "a4",
    margin: (top: 2.5cm, bottom: 2.5cm, left: 2cm, right: 2cm),
    header: context {
      if in-body.get() {
        place(top + left, dx: -2cm, dy: 0pt, block(width: 100% + 4.1cm, height: 1.75cm, fill: accent-colour))
        set text(fill: on-accent, font: headingFont, size: 9pt)
        align(horizon, grid(
          columns: (1fr, auto),
          [*#code* #h(0.4em) #title], [#series],
        ))
      }
    },
  )

  // Cover page
  #place(top + left, dx: -2cm, dy: -2.5cm, block(
    width: 100% + 4.1cm,
    height: 6cm,
    fill: accent-colour,
    inset: (x: 2.5cm, y: 1.5cm),
    align(bottom)[
      #text(size: 20pt, weight: "bold", font: headingFont, fill: on-accent)[#series]
      #v(-0.5em)
      #text(size: 14pt, weight: "bold", font: headingFont, fill: white)[#code]
    ],
  ))

  #align(center + horizon)[
    #text(size: 12pt, font: headingFont, fill: ink)[#subtitle]
    #v(1em)
    #text(size: 28pt, font: headingFont, fill: ink, weight: "bold")[#title]
    #v(0.5em)
    #line(length: 40%, stroke: accent-colour)
  ]

  #place(bottom + left, dx: -2cm, dy: 2.5cm, block(
    width: 100% + 4.1cm,
    height: 3.5cm,
    fill: accent-colour,
    inset: (x: 2.5cm, y: 1cm),
    align(horizon, grid(
      columns: (1fr, auto),
      align: horizon,
      gutter: 1em,
      [
        #text(size: 13pt, font: headingFont, fill: on-accent, weight: "bold")[#author]
        #v(-0.5em)
        #text(size: 9pt, font: headingFont, fill: on-accent)[#source-label: #source]
      ],
      text(size: 10pt, font: headingFont, fill: on-accent)[
        *#date-label:* \
        #date.display("[day]/[month]/[year]")
      ],
    )),
  ))

  #pagebreak()

  // Page number in footer, title page excluded from the count
  #counter(page).update(1)
  #set page(footer: context align(center, text(fill: ink, font: headingFont, size: 9pt)[-- #counter(page).get().first() --]))

  #outline(depth: 2)

  // Lists of figures/tables only if there are any
  #context {
    if counter(figure.where(kind: image)).final().at(0) > 0 {
      outline(title: i18n.figures, target: figure.where(kind: image))
    }
    if counter(figure.where(kind: table)).final().at(0) > 0 {
      outline(title: i18n.tables, target: figure.where(kind: table))
    }
  }

  #in-body.update(true)

  #pagebreak()
  #report
]
