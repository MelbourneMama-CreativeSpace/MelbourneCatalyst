import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listCompanies } from "@/lib/api";

export default async function CompaniesListPage() {
  const { items, total } = await listCompanies();

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
              &larr; Back
            </Link>
            <h1 className="mt-2 text-3xl font-bold">Companies</h1>
            <p className="mt-1 text-muted-foreground">
              {total === 0
                ? "No companies onboarded yet."
                : `${total} company profile${total === 1 ? "" : "s"} in the Knowledge Base.`}
            </p>
          </div>
          <Link
            href="/onboarding"
            className="inline-flex h-9 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/80"
          >
            + Onboard a company
          </Link>
        </div>

        {items.length === 0 ? (
          <p className="text-muted-foreground">
            Head to{" "}
            <Link href="/onboarding" className="underline">
              /onboarding
            </Link>{" "}
            to add your first company.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {items.map((company) => (
              <Link key={company.id} href={`/companies/${company.id}`}>
                <Card className="hover-lift cursor-pointer">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle>{company.name ?? company.url}</CardTitle>
                      <Badge variant={company.status === "failed" ? "outline" : "default"}>
                        {company.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="line-clamp-3 text-sm text-muted-foreground">
                      {company.summary ?? company.url}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
