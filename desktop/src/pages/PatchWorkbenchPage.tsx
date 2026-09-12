import { useCallback, useEffect, useRef, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import {
  PipelineApiError,
  cancelPipelineRun,
  createPipelineProject,
  detectEngine,
  fetchPipelineProfiles,
  fetchPipelineStatus,
  fetchPipelineToken,
  restorePipeline,
  startPipelineRun,
  subscribePipelineEvents,
  type PipelineProfile,
  type PipelineStatus,
} from '../lib/pipeline';

type Detection = { profile: string; score: number; capability: string; matched: string[] };

const STEP_LABELS: Record<string, string> = {
  DETECT: '引擎检测',
  UNPACK: '解包',
  EXTRACT: '文本提取',
  TRANSLATE: 'AI 翻译',
  INJECT: '注入回填',
  PACKAGE: '打包补丁',
};

export function PatchWorkbenchPage() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [gameDir, setGameDir] = useState('');
  const [projectDir, setProjectDir] = useState('');
  const [detections, setDetections] = useState<Detection[]>([]);
  const [profiles, setProfiles] = useState<PipelineProfile[]>([]);
  const [profileName, setProfileName] = useState('');
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<{ code: string; message: string } | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await fetchPipelineToken();
        const list = await fetchPipelineProfiles();
        if (!cancelled) {
          setProfiles(list);
          setReady(true);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const appendLog = useCallback((line: string) => {
    setLogs((prev) => [...prev.slice(-300), line]);
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  const handleBrowseGame = useCallback(async () => {
    const selected = await open({ directory: true });
    if (typeof selected === 'string') {
      setGameDir(selected);
    }
  }, []);

  const handleDetect = useCallback(async () => {
    setError('');
    try {
      const { results } = await detectEngine(gameDir);
      setDetections(results);
      if (results.length > 0) {
        setProfileName(results[0].profile);
      }
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
    }
  }, [gameDir]);

  const handleCreateProject = useCallback(async () => {
    setError('');
    try {
      const suggested = `${gameDir.replace(/[\\/]+$/, '')}_patch`;
      const { project_dir, profile } = await createPipelineProject({
        game_dir: gameDir,
        profile: profileName,
        project_dir: suggested,
      });
      setProjectDir(project_dir);
      const st = await fetchPipelineStatus(project_dir);
      setStatus(st);
      appendLog(`工程已创建:${project_dir}(引擎 ${profile})`);
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
    }
  }, [gameDir, profileName, appendLog]);

  const refreshStatus = useCallback(async (dir: string) => {
    try {
      const st = await fetchPipelineStatus(dir);
      setStatus(st);
    } catch {
      // 状态轮询失败不打断流程
    }
  }, []);

  // SSE 订阅:job 事件驱动状态刷新
  const activeProjectRef = useRef('');
  activeProjectRef.current = projectDir;
  useEffect(() => {
    if (!ready) {
      return () => undefined;
    }
    return subscribePipelineEvents(
      (event) => {
        if (event.event === 'log') {
          appendLog(`[${event.data.step}] ${event.data.message}`);
        } else if (event.event === 'job_started') {
          setRunning(true);
          setRunError(null);
          appendLog(`任务开始:${event.data.job_id}`);
        } else if (event.event === 'job_done') {
          setRunning(false);
          appendLog('任务完成 ✓');
          void refreshStatus(activeProjectRef.current);
        } else if (event.event === 'job_failed') {
          setRunning(false);
          setRunError({ code: event.data.code, message: event.data.message });
          appendLog(`任务失败:[${event.data.code}] ${event.data.message.split('\n')[0]}`);
        }
      },
      (message) => appendLog(`[连接] ${message}`),
    );
  }, [ready, appendLog, refreshStatus]);

  const handleRun = useCallback(
    async (fromStep?: string) => {
      if (!projectDir) {
        return;
      }
      setRunError(null);
      try {
        await startPipelineRun({ project_dir: projectDir, from_step: fromStep });
      } catch (err) {
        setRunError(
          err instanceof PipelineApiError
            ? { code: err.code, message: err.message }
            : { code: 'unknown', message: String(err) },
        );
      }
    },
    [projectDir],
  );

  const handleCancel = useCallback(async () => {
    setRunning(false);
    appendLog('已请求取消');
  }, [appendLog]);

  const handleRestore = useCallback(async () => {
    try {
      const { restored } = await restorePipeline(projectDir);
      appendLog(`已还原 ${restored} 个文件`);
      void refreshStatus(projectDir);
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
    }
  }, [projectDir, appendLog, refreshStatus]);

  const steps: Array<{ key: string; label: string }> = [
    'DETECT',
    'UNPACK',
    'EXTRACT',
    'TRANSLATE',
    'INJECT',
    'PACKAGE',
  ].map((key) => ({ key, label: STEP_LABELS[key] }));

  const stepState = (key: string): 'done' | 'failed' | 'pending' => {
    const entry = status?.steps?.[key];
    if (!entry) {
      return 'pending';
    }
    return entry.status === 'done' ? 'done' : entry.status === 'failed' ? 'failed' : 'pending';
  };

  return (
    <div className="page patch-page">
      <PageHeader
        title="补丁工作台"
        description="拖入游戏目录,自动识别引擎、提取文本、AI 翻译并产出中文补丁。"
      />

      {error && <div className="patch-page__error">{error}</div>}

      {!ready ? (
        <Panel title="连接后端">
          <p>正在向后端请求流水线凭据…</p>
          {error && <p className="patch-page__error">{error}</p>}
        </Panel>
      ) : (
        <>
          <Panel title="① 选择游戏">
              <div className="patch-page__row">
                <input
                  className="patch-page__input"
                  value={gameDir}
                  onChange={(event) => setGameDir(event.target.value)}
                  placeholder="游戏根目录(与游戏 exe 同级)"
                />
                <Button onClick={() => void handleBrowseGame()}>浏览…</Button>
                <Button variant="secondary" disabled={!gameDir || running} onClick={() => void handleDetect()}>
                  检测引擎
                </Button>
              </div>
            {detections.length > 0 && (
              <div className="patch-page__detections">
                {detections.map((item) => (
                  <label key={item.profile} className="patch-page__detection">
                    <input
                      type="radio"
                      checked={profileName === item.profile}
                      onChange={() => setProfileName(item.profile)}
                    />
                    <b>{item.profile}</b>
                    <StatusBadge label={`能力等级 ${item.capability}`} tone="completed" />
                    <span className="patch-page__muted">
                      依据: {item.matched.join(', ') || '-'}
                    </span>
                  </label>
                ))}
              </div>
            )}
            {profiles.length > 0 && (
              <div className="patch-page__row">
                <select
                  className="patch-page__input"
                  value={profileName}
                  onChange={(event) => setProfileName(event.target.value)}
                >
                  {profiles.map((profile) => (
                    <option key={profile.profile} value={profile.profile}>
                      {profile.profile}(能力等级 {profile.capability})
                    </option>
                  ))}
                </select>
                <Button
                  disabled={!gameDir || !profileName || running}
                  onClick={() => void handleCreateProject()}
                >
                  创建工程
                </Button>
              </div>
            )}
          </Panel>

          {projectDir && (
            <Panel title={`② 执行流水线(${projectDir})`}>
              <div className="patch-page__steps">
                {steps.map((step) => {
                  const state = stepState(step.key);
                  return (
                    <div key={step.key} className="patch-page__step">
                      <StatusBadge
                        label={step.label}
                        tone={state === 'done' ? 'completed' : state === 'failed' ? 'failed' : 'pending'}
                      />
                    </div>
                  );
                })}
              </div>
              <div className="patch-page__row">
                <Button disabled={running} onClick={() => void handleRun()}>
                  ▶ 运行全部
                </Button>
                <Button variant="secondary" disabled={running} onClick={() => void handleRun('TRANSLATE')}>
                  从「AI 翻译」重跑
                </Button>
                <Button variant="secondary" disabled={!running} onClick={() => void handleCancel()}>
                  取消
                </Button>
                <Button variant="secondary" onClick={() => void handleRestore()}>还原游戏文件</Button>
              </div>
              {runError && (
                <div className="patch-page__error">
                  [{runError.code}] {runError.message}
                </div>
              )}
              <div className="patch-page__log" ref={logRef}>
                {logs.length === 0 ? (
                  <span className="patch-page__muted">等待任务…</span>
                ) : (
                  logs.map((line, index) => <div key={`${index}-${line.slice(0, 12)}`}>{line}</div>)
                )}
              </div>
            </Panel>
          )}

          <Panel title="能力等级说明">
            <ul className="patch-page__capability">
              <li><b>L1 全自动</b>:专用工具具备提取+导入,完整流水线</li>
              <li><b>L2 全自动(受限)</b>:正则兜底提取+导入,受编码限制</li>
              <li><b>L3 半自动</b>:仅能提取并翻译,回封需人工</li>
              <li><b>L4 仅翻译</b>:自备 JSON 直接翻译</li>
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}
