import { Suspense } from "react";
import { CaseDetailView } from "@/components/case-detail";

async function CaseRoute({ params }: PageProps<"/cases/[id]">) {
  const { id } = await params;
  return <CaseDetailView id={id} />;
}

export default function CasePage(props: PageProps<"/cases/[id]">) {
  return (
    <Suspense fallback={<main className="p-8">Loading…</main>}>
      <CaseRoute {...props} />
    </Suspense>
  );
}
