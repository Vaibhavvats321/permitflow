import type { Metadata } from "next";
import { ReviewQueue } from "./queue-content";

export const metadata: Metadata = { title: "Review queue" };

export default function QueuePage() {
  return <ReviewQueue />;
}