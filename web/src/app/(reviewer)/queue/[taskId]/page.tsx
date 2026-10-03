import type { Metadata } from "next";
import { ReviewTaskDetail } from "./review-task-detail";

export const metadata: Metadata = { title: "Review task" };

export default function ReviewTaskPage() {
  return <ReviewTaskDetail />;
}