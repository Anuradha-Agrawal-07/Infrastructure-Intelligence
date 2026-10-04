import { useEffect, useState } from "react";
import { api } from "./api.js";
import AuthScreen from "./components/AuthScreen.jsx";
import TaskBoard from "./components/TaskBoard.jsx";
import NotificationPanel from "./components/NotificationPanel.jsx";

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [users, setUsers] = useState([]);
  const [checkingSession, setCheckingSession] = useState(true);
  const [notifRefreshKey, setNotifRefreshKey] = useState(0);

  async function loadSession() {
    if (!api.getToken()) {
      setCheckingSession(false);
      return;
    }
    try {
      const me = await api.me();
      setCurrentUser(me);
      const allUsers = await api.listUsers();
      setUsers(allUsers);
    } catch {
      api.setToken(null);
    } finally {
      setCheckingSession(false);
    }
  }

  useEffect(() => {
    loadSession();
  }, []);

  function handleAuthenticated() {
    setCheckingSession(true);
    loadSession();
  }

  function handleLogout() {
    api.setToken(null);
    setCurrentUser(null);
    setUsers([]);
  }

  if (checkingSession) {
    return <div className="loading-screen">Loading...</div>;
  }

  if (!currentUser) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>TaskFlow</h1>
        <div className="header-right">
          <NotificationPanel refreshKey={notifRefreshKey} />
          <span className="current-user">Signed in as {currentUser.username}</span>
          <button className="ghost" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>
      <main>
        <TaskBoard
          currentUser={currentUser}
          users={users}
          onTasksChanged={() => setNotifRefreshKey((k) => k + 1)}
        />
      </main>
    </div>
  );
}
