export default function Home() {
  return (
    <div className="flex min-h-full flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
          <p className="text-lg font-semibold tracking-tight text-slate-900">
            PermitFlow
          </p>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col justify-center px-6 py-16">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          City event permitting
        </p>
        <h1 className="mt-3 max-w-2xl text-4xl font-semibold tracking-tight text-slate-900">
          One application, every agency that needs to sign off.
        </h1>
        <p className="mt-4 max-w-xl text-lg leading-relaxed text-slate-600">
          PermitFlow is a multi-tenant web app where organizers request event
          permits and city agencies review them in one place.
        </p>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-5xl px-6 py-4 text-sm text-slate-500">
          PermitFlow
        </div>
      </footer>
    </div>
  );
}
