"use client";
import { StudyAssignments } from "@/components/study/StudyAssignments";
import { CrewSelector } from "@/components/crew/CrewSelector";
import { useNavigationRole } from "@/lib/navigation-role";
export default function AssignmentsPage() {
  const { role } = useNavigationRole();
  return role === "researcher" ? <StudyAssignments /> : <CrewSelector />;
}
