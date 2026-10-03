import Link from "next/link";
import {
  ArrowRight,
  Building2,
  ClipboardCheck,
  Clock,
  Route,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/layout/logo";
import { MarketingLinks } from "@/components/layout/sidebar";

/**
 * The public landing page.
 *
 * Written to explain what the product does for a city clerk or an event organiser
 * who has just been told to use it. The three capability sections mirror the three
 * things that are actually true of the backend: routing by event type, per-agency
 * tracking, and an immutable audit timeline.
 *
 * Static content, so it is a server component. No data fetch is needed and none
 * is invented — there is no "trusted by 400 cities" bar, because that would be a
 * lie about a demo project.
 */
export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="sticky top-0 z-40 border-b border-line bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <Wordmark />
          <nav aria-label="Account" className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild variant="primary" size="sm">
              <Link href="/login">
                Get started
                <ArrowRight aria-hidden />
              </Link>
            </Button>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        {/* A single soft wash. The rest of the page is flat surfaces; this is the
            only place colour is allowed to bleed, and it stays below 12% opacity. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 -top-40 h-[34rem]"
          style={{
            background:
              "radial-gradient(60% 100% at 50% 0%, rgb(99 102 241 / 0.09) 0%, rgb(99 102 241 / 0) 70%)",
          }}
        />

        <div className="relative mx-auto max-w-6xl px-5 pb-20 pt-20 sm:px-8 sm:pt-28">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[13px] text-ink-600">
              <ShieldCheck aria-hidden className="size-3.5 text-brand-600" />
              Multi-agency permit review
            </span>

            <h1 className="mt-6 text-4xl font-semibold leading-[1.1] tracking-tight text-ink-950 sm:text-[52px]">
              Event permits, without the
              <br />
              agency chase.
            </h1>

            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-600">
              Organisers submit an application once. PermitFlow routes it to the
              right agencies for the event, collects their decisions, and shows you
              precisely what is still outstanding.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button asChild variant="primary" size="lg">
                <Link href="/login">
                  Sign in to your account
                  <ArrowRight aria-hidden />
                </Link>
              </Button>
              <a
                href="#how-it-works"
                className="inline-flex h-10 items-center rounded-control px-3.5 text-sm font-medium text-ink-600 transition-colors hover:text-ink-900"
              >
                See how it works
              </a>
            </div>

            <p className="mt-6 text-[13px] text-ink-400">
              Organizer and agency reviewer accounts are provisioned by your city.
            </p>
          </div>
        </div>
      </section>

      {/* Capability sections */}
      <section id="how-it-works" className="border-y border-line bg-surface">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-semibold tracking-tight text-ink-950 sm:text-[32px]">
              Three things it does that email does not
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-ink-600">
              The hard part of a permit is not filling in the form. It is working
              out which agencies have to look at it, what each of them said, and
              what happens next. That is the whole product.
            </p>
          </div>

          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                icon: Route,
                title: "Routed by event type",
                body: "Each city configures which agencies review a marathon, a concert or a street fair. An event over 5,000 attendees automatically pulls in the fire department.",
                footnote: "Organised by your city's own routing rules",
              },
              {
                icon: Building2,
                title: "Per-agency progress",
                body: "Every application shows one row per agency with its decision, its comment and when it moved. No inferring an aggregate status from a missing reply.",
                footnote: "Approved, awaiting review, or blocked",
              },
              {
                icon: Clock,
                title: "An audit trail that holds up",
                body: "Edits, submissions and decisions are recorded with timestamps and authors. When an approval happened — and who made it — is a question with an answer.",
                footnote: "Append-only, never edited",
              },
            ].map((feature) => (
              <article
                key={feature.title}
                className="rounded-card border border-line bg-canvas p-6"
              >
                <span className="flex size-9 items-center justify-center rounded-control border border-line bg-surface">
                  <feature.icon aria-hidden className="size-4 text-brand-600" />
                </span>
                <h3 className="mt-5 text-[15px] font-semibold tracking-tight text-ink-900">
                  {feature.title}
                </h3>
                <p className="mt-2.5 text-sm leading-relaxed text-ink-600">
                  {feature.body}
                </p>
                <p className="mt-4 border-t border-line pt-3 text-[13px] text-ink-400">
                  {feature.footnote}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* How a reviewer sees it */}
      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
          <div>
            <span className="flex size-9 items-center justify-center rounded-control border border-line bg-surface">
              <ClipboardCheck aria-hidden className="size-4 text-brand-600" />
            </span>
            <h2 className="mt-5 text-2xl font-semibold tracking-tight text-ink-950">
              Built for both sides of the decision
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-ink-600">
              Organisers and reviewers get different workspaces, because they are
              answering different questions. An organiser asks{" "}
              <em className="text-ink-800">where is my permit?</em> A reviewer asks{" "}
              <em className="text-ink-800">what do I need to assess?</em>
            </p>
            <ul className="mt-6 space-y-3">
              {[
                "Organizers see a live count of which agency is still holding things up.",
                "Reviewers see only applications assigned to their own agency, with a required comment on every decision.",
                "Changes requested sends the application straight back for correction and resubmission.",
              ].map((point) => (
                <li key={point} className="flex gap-3 text-sm leading-relaxed text-ink-600">
                  <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-brand-500" />
                  {point}
                </li>
              ))}
            </ul>
          </div>

          {/* A representative queue, rendered as real markup rather than a
              screenshot so it stays sharp and legible on any display. */}
          <div className="rounded-panel border border-line bg-surface p-5 shadow-raised">
            <div className="flex items-center justify-between border-b border-line pb-4">
              <div>
                <p className="text-sm font-semibold text-ink-900">Review queue</p>
                <p className="mt-0.5 text-[13px] text-ink-500">
                  Fire Department · 4 awaiting review
                </p>
              </div>
              <span className="rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700">
                4 open
              </span>
            </div>

            <ul className="divide-y divide-line">
              {[
                { name: "Riverside Half Marathon", type: "Marathon", when: "12 Apr", tone: "bg-brand-50 text-brand-700" },
                { name: "Harbour Lights Festival", type: "Street Fair", when: "28 Apr", tone: "bg-brand-50 text-brand-700" },
                { name: "Autumn Sound Series", type: "Concert", when: "03 May", tone: "bg-brand-50 text-brand-700" },
                { name: "Marina Night Market", type: "Street Fair", when: "09 May", tone: "bg-brand-50 text-brand-700" },
              ].map((task) => (
                <li key={task.name} className="flex items-center gap-4 py-3.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink-900">
                      {task.name}
                    </p>
                    <span className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[11px] ${task.tone}`}>
                      {task.type}
                    </span>
                  </div>
                  <span className="tabular shrink-0 text-[13px] text-ink-500">{task.when}</span>
                </li>
              ))}
            </ul>

            <p className="mt-4 border-t border-line pt-3 text-[13px] text-ink-400">
              Example queue content, shown for illustration.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-5 py-16 sm:px-8 lg:flex-row lg:items-center">
          <div className="max-w-xl">
            <h2 className="text-2xl font-semibold tracking-tight text-ink-950">
              Ready to see your applications in one place?
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-600">
              Sign in with the account your city provisioned for you.
            </p>
          </div>
          <Button asChild variant="primary" size="lg">
            <Link href="/login">
              Sign in
              <ArrowRight aria-hidden />
            </Link>
          </Button>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-5 py-10 sm:px-8 md:flex-row md:items-center">
          <Wordmark />
          <MarketingLinks />
        </div>
      </footer>
    </div>
  );
}