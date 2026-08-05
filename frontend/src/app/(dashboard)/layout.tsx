import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { LayoutWrapper } from "@/components/layout-wrapper";
import { createClient } from "@/lib/supabase/server";

// Every route under this group is auth-gated by `proxy.ts` — an
// unauthenticated request never reaches this layout. `user` is fetched
// defensively anyway (never assumed non-null) since a server component
// shouldn't crash on a race between the proxy check and this render.
export default async function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const fullName = user?.user_metadata?.full_name;

  return (
    <LayoutWrapper>
      <DashboardSidebar
        initialEmail={user?.email ?? null}
        initialName={typeof fullName === "string" && fullName ? fullName : null}
      />
      <main className="min-w-0 flex-1">{children}</main>
    </LayoutWrapper>
  );
}
