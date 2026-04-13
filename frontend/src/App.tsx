import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import EmailDetail from './pages/EmailDetail';
import ConversationView from './pages/ConversationView';
import DraftEditor from './pages/DraftEditor';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/emails/:id" element={<EmailDetail />} />
          <Route path="/conversations" element={<ConversationView />} />
          <Route path="/conversations/:email" element={<ConversationView />} />
          <Route path="/drafts/:uid/edit" element={<DraftEditor />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
