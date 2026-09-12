/** 桌面端能力封装:系统通知(M6)与自动更新检查。

浏览器 dev 态自动降级为 Web Notification / 静默跳过。
*/

export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

export async function notifySystem(title: string, body: string): Promise<void> {
  try {
    if (isTauri()) {
      const mod = await import('@tauri-apps/plugin-notification');
      let granted = await mod.isPermissionGranted();
      if (!granted) {
        granted = (await mod.requestPermission()) === 'granted';
      }
      if (granted) {
        mod.sendNotification({ title, body });
      }
      return;
    }
    if (typeof Notification !== 'undefined') {
      if (Notification.permission === 'granted') {
        new Notification(title, { body });
      } else if (Notification.permission !== 'denied') {
        const perm = await Notification.requestPermission();
        if (perm === 'granted') new Notification(title, { body });
      }
    }
  } catch {
    // 通知不可用时静默跳过
  }
}

/** 启动时静默检查更新;有新版则发系统通知(仅 Tauri 打包态可用)。 */
export async function checkForUpdateSilent(currentVersion: string): Promise<void> {
  if (!isTauri()) return;
  try {
    const { check } = await import('@tauri-apps/plugin-updater');
    const update = await check();
    if (update?.version && update.version !== currentVersion) {
      await notifySystem(
        'GalTransl 有新版本',
        `当前 ${currentVersion} → 最新 ${update.version}。请到 GitHub Releases 下载安装包升级。`,
      );
    }
  } catch {
    // 无网络/无发布版本等情况静默跳过
  }
}
