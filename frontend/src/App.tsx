import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { AppRouter } from "./app/router";

function App() {
  return (
    <AppErrorBoundary>
      <AppRouter />
    </AppErrorBoundary>
  );
}

export default App;
