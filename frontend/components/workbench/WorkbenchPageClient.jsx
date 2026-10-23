"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BarChart3, Binary, Braces, Database, FlaskConical, Layers, ListTree, Sigma, Wand2 } from "lucide-react";
import PageHeader from "@/components/ui/PageHeader";
import Tabs, { TabPanel } from "@/components/ui/Tabs";
import BooleanPanel from "./BooleanPanel";
import CosinePanel from "./CosinePanel";
import EvaluationPanel from "./EvaluationPanel";
import ExpansionPanel from "./ExpansionPanel";
import InvertedIndexPanel from "./InvertedIndexPanel";
import PreprocessingPanel from "./PreprocessingPanel";
import RocchioPanel from "./RocchioPanel";
import TfidfPanel from "./TfidfPanel";
import WildcardPanel from "./WildcardPanel";

const TABS = [
  { id: "preprocessing", label: "Preprocessing", icon: Wand2, Panel: PreprocessingPanel },
  { id: "boolean", label: "Boolean retrieval", icon: Binary, Panel: BooleanPanel },
  { id: "index", label: "Inverted index", icon: Database, Panel: InvertedIndexPanel },
  { id: "wildcard", label: "Prefix / wildcard", icon: Braces, Panel: WildcardPanel },
  { id: "tfidf", label: "TF-IDF", icon: Sigma, Panel: TfidfPanel },
  { id: "cosine", label: "Cosine similarity", icon: ListTree, Panel: CosinePanel },
  { id: "expansion", label: "Query expansion", icon: Layers, Panel: ExpansionPanel },
  { id: "rocchio", label: "Rocchio", icon: FlaskConical, Panel: RocchioPanel },
  { id: "evaluation", label: "Evaluation", icon: BarChart3, Panel: EvaluationPanel },
];

/** The active tab lives in the URL (?tab=rocchio) so a workbench view can be shared or bookmarked. */
export default function WorkbenchPageClient() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const requested = params.get("tab");
  const active = TABS.some((t) => t.id === requested) ? requested : TABS[0].id;

  const select = (id) => router.replace(`${pathname}?tab=${id}`, { scroll: false });

  return (
    <>
      <PageHeader
        title="IR Workbench"
        description="Inspect every stage of the retrieval pipeline. All numbers come from the backend implementation; nothing is recomputed in the browser."
        breadcrumbs={[{ label: "Workbench" }]}
      />
      <Tabs tabs={TABS} value={active} onChange={select} label="Workbench sections" idPrefix="wb" />
      {TABS.map(({ id, Panel }) => (
        <TabPanel key={id} id={id} active={active === id} idPrefix="wb">
          <Panel />
        </TabPanel>
      ))}
    </>
  );
}
