import type { Metadata } from "next";
import { ApplicationDetail } from "./application-detail";

export const metadata: Metadata = { title: "Application" };

export default function ApplicationPage() {
  return <ApplicationDetail />;
}