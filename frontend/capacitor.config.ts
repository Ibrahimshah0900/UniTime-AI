import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.unitimeai.mobile',
  appName: 'UniTime-AI',
  webDir: 'dist',
  ...(process.env.CAPACITOR_DEV_CLEARTEXT === '1' ? { server: { cleartext: true } } : {})
};

export default config;
