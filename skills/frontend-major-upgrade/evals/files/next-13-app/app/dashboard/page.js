import { cookies, headers } from 'next/headers';
import Card from '../../components/Card';

export default function DashboardPage() {
  const theme = cookies().get('theme');
  const agent = headers().get('user-agent');
  return (
    <main data-theme={theme ? theme.value : 'light'}>
      <Card title="Browser" body={agent} />
    </main>
  );
}
