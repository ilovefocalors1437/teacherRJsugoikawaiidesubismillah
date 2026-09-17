import { useEffect, useState } from "react";
import Landing from "./pages/Landing.jsx";
import Practice from "./pages/Practice.jsx";
import Theory from "./pages/Theory.jsx";
import TutorBook from "./pages/TutorBook.jsx";
import TutorReader from "./pages/TutorReader.jsx";
import Clarify from "./pages/Clarify.jsx";
import AmbientGlow from "./components/AmbientGlow.jsx";

/* Tiny hash router — #/ , #/practice , #/theory.
   Hash-based so the built dist/ works from Flask or file:// alike. */
function useHashRoute() {
  const read = () => window.location.hash.replace(/^#/, "") || "/";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export default function App() {
  const route = useHashRoute();
  useEffect(() => { window.scrollTo(0, 0); }, [route]);

  const chapterMatch = route.match(/^\/tutor\/(.+)$/);
  const chapterId = chapterMatch ? chapterMatch[1] : null;

  const page = route.startsWith("/practice") ? <Practice />
    : route.startsWith("/clarify") ? <Clarify />
    : route.startsWith("/tutor/") && chapterId ? <TutorReader chapterId={chapterId} />
    : route.startsWith("/tutor") ? <TutorBook />
    : route.startsWith("/theory") ? <Theory />
    : <Landing />;

  return (
    <>
      {/* Rendered once, outside the routed page, so the ambient light
          persists across route changes and sits behind all content. */}
      <AmbientGlow />
      {page}
    </>
  );
}
