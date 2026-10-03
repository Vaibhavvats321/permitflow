import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { SessionProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/ui/toast";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "PermitFlow",
    template: "%s — PermitFlow",
  },
  description:
    "Submit event permit applications once and track every agency decision in a single timeline.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} h-full antialiased`}>
      <body className="min-h-full">
        {/*
          The providers sit at the root rather than inside each route group, so a
          sign-out triggered from any workspace — including one reached after a
          hard refresh — reaches the same context that `useSession` reads.
        */}
        <SessionProvider>
          <ToastProvider>{children}</ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}