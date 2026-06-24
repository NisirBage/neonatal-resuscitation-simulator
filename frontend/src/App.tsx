import { InstructorDashboard } from "./pages/InstructorDashboard";
import { StudentDashboard } from "./pages/StudentDashboard";

export default function App() {
  const isInstructor =
    new URLSearchParams(window.location.search).get("role") === "instructor";
  return isInstructor ? <InstructorDashboard /> : <StudentDashboard />;
}
