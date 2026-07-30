export default function KnowledgeAuditLoading() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-12">
        <div className="mb-6 h-4 w-32 animate-pulse rounded bg-muted" />
        <div className="mb-8 h-10 w-72 animate-pulse rounded-lg bg-muted" />
        <div className="flex flex-col gap-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      </div>
    </div>
  );
}
