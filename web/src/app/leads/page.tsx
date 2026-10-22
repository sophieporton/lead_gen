import type { Metadata } from "next";
import { PageTitle } from "@/components/ui";
import { data } from "@/lib/data";
import LeadsExplorer from "./LeadsExplorer";

export const metadata: Metadata = { title: "Leads | Lead Research Pipeline" };

export default function LeadsPage() {
  return (
    <>
      <PageTitle
        title="Scored leads"
        intro={
          <>
            {data.leads.length} companies with a verified website, each scored against five example customer
            descriptions. Pick one to re-rank the list. Every score has a one-line reason, and leads scoring 50
            or more get a draft opening line for a cold email.
          </>
        }
      />
      <LeadsExplorer />
    </>
  );
}
