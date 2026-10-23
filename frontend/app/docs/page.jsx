import ArchitectureDiagram from "@/components/docs/ArchitectureDiagram";
import Formula from "@/components/ui/Formula";
import PageHeader from "@/components/ui/PageHeader";
import { DEMO_FLOW, DOC_SECTIONS, VIVA_QUESTIONS } from "@/lib/docsContent";

export const metadata = { title: "Documentation and viva" };

const TOC = [
  ...DOC_SECTIONS.map((s) => ({ id: s.id, title: s.title })),
  { id: "viva", title: "Viva questions" },
  { id: "demo", title: "Demo flow" },
];

function SectionHeading({ id, children }) {
  return (
    <h2 id={id} className="scroll-mt-20 border-b border-mute-line pb-1 text-xl font-semibold text-navy-800">
      {children}
    </h2>
  );
}

export default function DocsPage() {
  return (
    <>
      <PageHeader
        title="Documentation and viva"
        description="Technical reference for the system, with the questions and demo flow for the IR viva."
        breadcrumbs={[{ label: "Documentation" }]}
      />
      <div className="grid gap-8 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav aria-label="Documentation sections" className="lg:sticky lg:top-20 lg:self-start">
          <details className="rounded-md border border-mute-line bg-white lg:hidden">
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium">On this page</summary>
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-mute-line p-3 text-sm">
              {TOC.map((t) => (
                <li key={t.id}>
                  <a href={`#${t.id}`} className="text-teal-700 hover:underline">{t.title}</a>
                </li>
              ))}
            </ul>
          </details>
          <ul className="hidden max-h-[calc(100vh-7rem)] space-y-1 overflow-y-auto border-l border-mute-line pl-3 text-sm lg:block">
            {TOC.map((t) => (
              <li key={t.id}>
                <a href={`#${t.id}`} className="block py-0.5 text-ink-soft hover:text-teal-700">{t.title}</a>
              </li>
            ))}
          </ul>
        </nav>

        <article className="min-w-0 space-y-8">
          {DOC_SECTIONS.map((s) => (
            <section key={s.id} aria-labelledby={s.id} className="space-y-3">
              <SectionHeading id={s.id}>{s.title}</SectionHeading>
              {s.paragraphs?.map((p) => (
                <p key={p.slice(0, 40)} className="max-w-3xl leading-relaxed text-ink-soft">{p}</p>
              ))}
              {s.diagram && <ArchitectureDiagram />}
              {s.formulas?.map((f) => (
                <Formula key={f} className="max-w-xl">{f}</Formula>
              ))}
              {s.bullets && (
                <ul className="max-w-3xl list-disc space-y-1 pl-5 text-ink-soft">
                  {s.bullets.map((b) => (
                    <li key={b.slice(0, 40)}>{b}</li>
                  ))}
                </ul>
              )}
            </section>
          ))}

          <section aria-labelledby="viva" className="space-y-3">
            <SectionHeading id="viva">Viva questions</SectionHeading>
            <div className="max-w-3xl divide-y divide-mute-line rounded-md border border-mute-line bg-white">
              {VIVA_QUESTIONS.map((item) => (
                <details key={item.q} className="group px-4 py-2">
                  <summary className="cursor-pointer py-1 font-medium text-navy-700 marker:text-teal-600">{item.q}</summary>
                  <p className="pb-2 pt-1 text-sm leading-relaxed text-ink-soft">{item.a}</p>
                </details>
              ))}
            </div>
          </section>

          <section aria-labelledby="demo" className="space-y-3">
            <SectionHeading id="demo">Demo flow</SectionHeading>
            <ol className="max-w-3xl space-y-2">
              {DEMO_FLOW.map((d, i) => (
                <li key={d.step} className="flex gap-3 rounded-md border border-mute-line bg-white px-4 py-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-navy-800 font-mono text-xs text-white" aria-hidden="true">
                    {i + 1}
                  </span>
                  <div>
                    <p className="font-medium text-navy-800">{d.step}</p>
                    <p className="text-sm text-ink-soft">{d.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </article>
      </div>
    </>
  );
}
