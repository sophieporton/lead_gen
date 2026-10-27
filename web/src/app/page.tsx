import Link from "next/link";
import { data } from "@/lib/data";
import LeadFinder from "./LeadFinder";

export default function Home() {
  return (
    <>
      <div className="mb-8 max-w-3xl">
        <p className="text-sm font-medium text-accent-ink">Interactive demo</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Tell it what you sell. Get a list of companies likely to buy it.
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-ink-2">
          An AI research pipeline that finds small businesses, reads their websites and scores each one against
          your ideal customer, with a reason for every score and a draft opening line. This demo searches{" "}
          {data.funnel.website_verified} researched companies in the North East of England.{" "}
          <Link href="/how-it-works" className="text-accent-ink underline underline-offset-2">How it works</Link>
        </p>
      </div>
      <LeadFinder />
    </>
  );
}
