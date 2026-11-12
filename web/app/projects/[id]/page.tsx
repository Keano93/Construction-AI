import { redirect } from "next/navigation";

// The review queue is the landing page for a project.
export default async function ProjectHome({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/projects/${id}/inbox`);
}
