"use client";

import { ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useSession } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { homePathForRole } from "@/lib/status";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/input";

/**
 * Login.
 *
 * One form, no role selector. The API decides what an account may see, and a role
 * picker on the sign-in screen would be a lie — choosing "Reviewer" here would not
 * grant reviewer access to anything.
 *
 * The split layout is deliberate rather than decorative: the left panel explains
 * the product in one sentence for someone who landed here directly, and the right
 * panel is the form for someone who already knows. It also keeps the form above
 * the fold on a laptop, which a centred card under a marketing banner would not.
 */

export function LoginForm() {
  const router = useRouter();
  const { signIn } = useSession();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError>();
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) return;

    setError(undefined);
    setIsSubmitting(true);

    try {
      const identity = await signIn(email, password);
      // Route by the role the server returned, not by anything the form knew.
      router.replace(homePathForRole(identity.role));
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause
          : new ApiError(0, "Could not reach the sign-in service."),
      );
      // The password is cleared so a retry does not resubmit a value the server
      // has already rejected, and so it does not linger in the DOM.
      setPassword("");
    } finally {
      setIsSubmitting(false);
    }
  }

  const isNetworkError = error?.isNetwork;

  return (
    <div className="w-full max-w-sm">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-950">Sign in</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-500">
          Use the account your city issued you. Organizers apply for permits;
          agency reviewers decide on them.
        </p>
      </div>

      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-control border border-critical/20 bg-critical-soft px-3.5 py-3"
          >
            <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-critical" />
            <div className="space-y-1">
              <p className="text-[13px] font-semibold text-critical-ink">
                {isNetworkError
                  ? "Cannot reach PermitFlow"
                  : error.status === 401
                    ? "Email or password is incorrect"
                    : "Could not sign you in"}
              </p>
              <p className="text-[13px] leading-relaxed text-critical-ink/85">
                {error.message}
              </p>
            </div>
          </div>
        )}

        <TextField
          name="email"
          label="Work email"
          type="email"
          autoComplete="username"
          inputMode="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@city.gov"
          disabled={isSubmitting}
        />

        <TextField
          name="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={isSubmitting}
        />

        <Button
          type="submit"
          variant="primary"
          size="lg"
          block
          loading={isSubmitting}
          iconAfter={isSubmitting ? undefined : <ArrowRight />}
        >
          {isSubmitting ? "Signing in" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-[13px] leading-relaxed text-ink-400">
        Sessions last 60 minutes. Your city&rsquo;s accounts are created by its
        administrator.
      </p>
    </div>
  );
}

/** The product half of the login screen. Hidden below `lg`, where it is noise. */
export function LoginAside() {
  return (
    <div className="relative hidden flex-1 flex-col justify-between overflow-hidden border-r border-line bg-surface p-12 lg:flex">
      {/* A single soft radial wash. Flat surfaces everywhere else keep this from
          reading as a gradient-heavy marketing page. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-24 size-96 rounded-full opacity-70"
        style={{
          background:
            "radial-gradient(circle, rgb(99 102 241 / 0.10) 0%, rgb(99 102 241 / 0) 70%)",
        }}
      />

      <div className="relative">
        <p className="text-[13px] font-medium text-ink-500">
          Permit application review for cities
        </p>
      </div>

      <div className="relative max-w-lg space-y-6">
        <h2 className="text-[32px] font-semibold leading-[1.15] tracking-tight text-ink-950">
          One application, every agency decision in one place.
        </h2>
        <p className="text-[15px] leading-relaxed text-ink-500">
          Submit an event once. PermitFlow routes it to the agencies your city has
          designated, collects their decisions, and shows you exactly what is still
          outstanding — so chasing a permit stops being a task in your inbox.
        </p>

        <dl className="grid grid-cols-3 gap-6 border-t border-line pt-6">
          {[
            { term: "Every agency", detail: "Decisions gathered in one timeline" },
            { term: "Visible progress", detail: "Pending, approved or blocked" },
            { term: "Full history", detail: "Every edit and decision, timestamped" },
          ].map((item) => (
            <div key={item.term} className="space-y-1">
              <dt className="text-[13px] font-semibold text-ink-900">{item.term}</dt>
              <dd className="text-[13px] leading-relaxed text-ink-500">{item.detail}</dd>
            </div>
          ))}
        </dl>
      </div>

      <p className="relative flex items-center gap-2 text-[13px] text-ink-400">
        <ShieldCheck aria-hidden className="size-4" />
        Each city&rsquo;s data is isolated to its own tenants.
      </p>
    </div>
  );
}

/** A link back to marketing, for the login page's footer. */
export function BackToSite() {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-1.5 text-[13px] text-ink-400 transition-colors hover:text-ink-700"
    >
      <ArrowRight aria-hidden className="size-3.5 rotate-180" />
      Back to overview
    </Link>
  );
}