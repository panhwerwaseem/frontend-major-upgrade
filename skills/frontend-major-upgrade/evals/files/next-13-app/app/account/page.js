import { cookies } from 'next/headers';

export default async function AccountPage() {
  const cookieStore = await cookies();
  const session = cookieStore.get('session');
  return <main>{session ? 'Signed in' : 'Signed out'}</main>;
}
