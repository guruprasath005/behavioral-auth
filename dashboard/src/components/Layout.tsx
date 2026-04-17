import { NavLink, Outlet, useMatch } from "react-router-dom";

function navClass({ isActive }: { isActive: boolean }): string {
  return `block rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
    isActive
      ? "border border-white/70 bg-white/50 text-indigo-700 shadow-glass-sm"
      : "border border-transparent text-slate-600 hover:border-white/40 hover:bg-white/35 hover:text-slate-800"
  }`;
}

export function Layout() {
  const sessionMatch = useMatch({ path: "/sessions/:sessionId/*", end: false });
  const sessionId = sessionMatch?.params.sessionId;

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-white/40 bg-white/35 shadow-glass backdrop-blur-2xl backdrop-saturate-150">
        <div className="border-b border-white/40 p-5">
          <h1 className="text-[0.95rem] font-semibold tracking-tight text-slate-900">
            Behavioral Auth
          </h1>
          <p className="mt-1 text-xs font-medium text-slate-500">
            Security dashboard
          </p>
        </div>
        <nav className="flex flex-col gap-1.5 p-4">
          <NavLink to="/sessions" className={navClass} end>
            Sessions
          </NavLink>
          {sessionId ? (
            <>
              <NavLink
                to={`/sessions/${sessionId}/alerts`}
                className={navClass}
              >
                Alerts &amp; audit
              </NavLink>
              <NavLink to={`/sessions/${sessionId}/live`} className={navClass}>
                Live monitor
              </NavLink>
            </>
          ) : (
            <>
              <p className="px-3 py-2 text-xs leading-relaxed text-slate-500">
                Open a session to use Alerts &amp; Live.
              </p>
            </>
          )}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto p-6 md:p-8">
        <Outlet />
      </main>
    </div>
  );
}
