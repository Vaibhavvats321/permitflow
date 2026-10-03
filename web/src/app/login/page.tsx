import { LoginAside, LoginForm, BackToSite } from "./login-form";
import { RequireAnonymous } from "@/components/layout/guards";
import { Wordmark } from "@/components/layout/logo";

export const metadata = {
  title: "Sign in — PermitFlow",
};

export default function LoginPage() {
  return (
    <RequireAnonymous>
      <div className="flex min-h-dvh flex-col lg:flex-row">
        <LoginAside />
        <div className="flex flex-1 flex-col bg-canvas">
          <header className="flex items-center justify-between px-6 py-6 sm:px-10">
            <Wordmark className="lg:invisible" />
            <BackToSite />
          </header>
          <div className="flex flex-1 items-center justify-center px-6 pb-16 sm:px-10">
            <LoginForm />
          </div>
        </div>
      </div>
    </RequireAnonymous>
  );
}