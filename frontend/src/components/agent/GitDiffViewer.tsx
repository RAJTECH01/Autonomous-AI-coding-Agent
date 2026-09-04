import React, { useState } from 'react';
import { GitBranch, GitCommit, Shield, ShieldAlert, UploadCloud, FileCode, RefreshCw } from 'lucide-react';
import { GitDiffResult, GitState, GitCommitMetadata } from '../../types/git';

interface GitDiffViewerProps {
  gitState?: GitState;
  diffResult?: GitDiffResult;
  commits?: GitCommitMetadata[];
  onRefreshDiff?: () => void;
  onAuthorizePush?: (remote: string, branch: string) => void;
}

export const GitDiffViewer: React.FC<GitDiffViewerProps> = ({
  gitState = {
    commit_hash: 'a1b2c3d4e5f6',
    branch_name: 'agent/task-auth-refresh',
    is_dirty: true,
    staged_files: ['backend/app/api/v1/endpoints/auth.py'],
    unstaged_files: ['backend/tests/test_auth.py'],
    untracked_files: ['backend/app/schemas/token.py'],
    timestamp: new Date().toISOString(),
  },
  diffResult = {
    diff_text: `--- a/backend/app/api/v1/endpoints/auth.py\n+++ b/backend/app/api/v1/endpoints/auth.py\n@@ -45,8 +45,14 @@ async def refresh_token(request: RefreshTokenRequest):\n-    # Old unvalidated refresh token handling\n-    user = decode_token(request.token)\n+    # New validated token rotation with database revocation check\n+    user = await token_service.verify_and_rotate_refresh_token(request.token)\n+    if not user:\n+        raise HTTPException(status_code=401, detail="Token revoked or expired")\n+    return TokenResponse(access_token=create_access_token(user.id), refresh_token=user.new_refresh_token)`,
    files_changed: ['backend/app/api/v1/endpoints/auth.py', 'backend/tests/test_auth.py', 'backend/app/schemas/token.py'],
    file_stats: [
      { file_path: 'backend/app/api/v1/endpoints/auth.py', additions: 14, deletions: 2, binary: false },
      { file_path: 'backend/tests/test_auth.py', additions: 28, deletions: 0, binary: false },
      { file_path: 'backend/app/schemas/token.py', additions: 12, deletions: 0, binary: false },
    ],
    total_additions: 54,
    total_deletions: 2,
    success: true,
  },
  commits = [
    {
      commit_hash: 'f9e8d7c6b5a4',
      branch_name: 'agent/task-auth-refresh',
      message: 'feat(auth): Implement token rotation and revocation database validation',
      author_name: 'Autonomous Agent',
      author_email: 'agent@autonomous.local',
      files_changed: ['backend/app/api/v1/endpoints/auth.py', 'backend/tests/test_auth.py'],
      timestamp: new Date().toISOString(),
    }
  ],
  onRefreshDiff,
  onAuthorizePush,
}) => {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [showPushModal, setShowPushModal] = useState(false);
  const [pushRemote, setPushRemote] = useState('origin');
  const [confirmPushChecked, setConfirmPushChecked] = useState(false);
  const [pushStatusMessage, setPushStatusMessage] = useState('');

  const isProtectedBranch = ['main', 'master', 'production', 'release', 'staging'].includes(
    gitState.branch_name.toLowerCase()
  );

  const handleConfirmPush = (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirmPushChecked) return;
    if (onAuthorizePush) {
      onAuthorizePush(pushRemote, gitState.branch_name);
    }
    setPushStatusMessage(`Push authorized and sent to remote '${pushRemote}' for branch '${gitState.branch_name}'.`);
    setTimeout(() => {
      setShowPushModal(false);
      setConfirmPushChecked(false);
      setPushStatusMessage('');
    }, 2500);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Git Status Header Card */}
      <div className="glass-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1.25rem 1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
          <div style={{
            background: 'linear-gradient(135deg, rgba(168,85,247,0.3) 0%, rgba(126,34,206,0.3) 100%)',
            padding: '0.6rem',
            borderRadius: '14px',
            border: '1px solid rgba(192,132,252,0.4)',
            boxShadow: 'var(--skeuo-shadow-raised)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <GitBranch size={24} color="#c084fc" />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontSize: '1.1rem', fontWeight: 800, color: '#ffffff' }}>
                {gitState.branch_name}
              </span>

              {isProtectedBranch ? (
                <span style={{
                  fontSize: '0.72rem',
                  padding: '0.2rem 0.65rem',
                  borderRadius: '12px',
                  background: 'linear-gradient(135deg, rgba(244, 63, 94, 0.3) 0%, rgba(225, 29, 72, 0.3) 100%)',
                  color: '#fb7185',
                  border: '1px solid rgba(251, 113, 133, 0.4)',
                  fontWeight: 800,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem'
                }}>
                  <ShieldAlert size={12} /> PROTECTED BRANCH (READ-ONLY GUARD)
                </span>
              ) : (
                <span style={{
                  fontSize: '0.72rem',
                  padding: '0.2rem 0.65rem',
                  borderRadius: '12px',
                  background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.3) 0%, rgba(126, 34, 206, 0.3) 100%)',
                  color: '#f3e8ff',
                  border: '1px solid rgba(192, 132, 252, 0.4)',
                  fontWeight: 800,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem'
                }}>
                  <Shield size={12} /> ISOLATED TASK WORKSPACE
                </span>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '0.35rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              <span>HEAD: <code style={{ color: '#c084fc', fontWeight: 700 }}>{gitState.commit_hash.slice(0, 7) || 'HEAD'}</code></span>
              <span>•</span>
              <span>Total Changes: <strong style={{ color: '#ffffff' }}>{diffResult.files_changed.length} Files</strong></span>
              <span>•</span>
              <span style={{ color: '#34d399', fontWeight: 700 }}>+{diffResult.total_additions}</span>
              <span style={{ color: '#fb7185', fontWeight: 700 }}>-{diffResult.total_deletions}</span>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {onRefreshDiff && (
            <button
              onClick={onRefreshDiff}
              className="btn btn-secondary"
              style={{ padding: '0.55rem 0.95rem', fontSize: '0.85rem' }}
            >
              <RefreshCw size={15} /> Refresh Diff
            </button>
          )}

          <button
            onClick={() => setShowPushModal(true)}
            className="btn"
            style={{ padding: '0.55rem 1.15rem', fontSize: '0.85rem' }}
          >
            <UploadCloud size={16} /> Authorize Push to Remote
          </button>
        </div>
      </div>

      {/* Main Grid: File Tree & Diff Viewer */}
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '1.5rem' }}>
        {/* Left Column: Changed Files List */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem', padding: '1.25rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FileCode size={16} color="#c084fc" /> Changed Files ({diffResult.file_stats.length})
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {diffResult.file_stats.map((f, idx) => (
              <div
                key={idx}
                onClick={() => setSelectedFile(selectedFile === f.file_path ? null : f.file_path)}
                style={{
                  padding: '0.75rem 0.9rem',
                  borderRadius: '10px',
                  background: selectedFile === f.file_path ? 'linear-gradient(135deg, rgba(168, 85, 247, 0.25) 0%, rgba(126, 34, 206, 0.25) 100%)' : 'rgba(3, 1, 6, 0.75)',
                  border: selectedFile === f.file_path ? '1px solid rgba(192, 132, 252, 0.5)' : '1px solid var(--glass-border)',
                  boxShadow: selectedFile === f.file_path ? '0 4px 12px rgba(168, 85, 247, 0.2)' : 'var(--skeuo-shadow-inset)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem', maxWidth: '70%', overflow: 'hidden' }}>
                  <span style={{ fontSize: '0.84rem', fontWeight: 700, color: '#ffffff', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                    {f.file_path.split('/').pop()}
                  </span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                    {f.file_path}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', fontWeight: 800 }}>
                  <span style={{ color: '#34d399' }}>+{f.additions}</span>
                  <span style={{ color: '#fb7185' }}>-{f.deletions}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Code Diff Stream & Commit Log */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Unified Diff View */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1.25rem' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Unified Diff Code View
            </h3>

            <div className="skeuo-inset" style={{ padding: 0, overflow: 'hidden', borderRadius: '12px' }}>
              <pre style={{
                padding: '1.25rem',
                margin: 0,
                fontSize: '0.84rem',
                lineHeight: '1.6',
                fontFamily: 'var(--font-mono)',
                color: '#ffffff',
                overflowX: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all'
              }}>
                {diffResult.diff_text.split('\n').map((line, idx) => {
                  let bg = 'transparent';
                  let color = '#e2e8f0';
                  if (line.startsWith('+') && !line.startsWith('+++')) {
                    bg = 'rgba(52, 211, 153, 0.18)';
                    color = '#34d399';
                  } else if (line.startsWith('-') && !line.startsWith('---')) {
                    bg = 'rgba(244, 63, 94, 0.18)';
                    color = '#fb7185';
                  } else if (line.startsWith('@@')) {
                    bg = 'rgba(168, 85, 247, 0.2)';
                    color = '#c084fc';
                  }
                  return (
                    <div key={idx} style={{ background: bg, color: color, padding: '0.1rem 0.5rem', borderRadius: '2px' }}>
                      {line}
                    </div>
                  );
                })}
              </pre>
            </div>
          </div>

          {/* Commit Metadata History */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1.25rem' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <GitCommit size={16} color="#c084fc" /> Recorded Commit Metadata ({commits.length})
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {commits.map((c, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: '0.9rem 1.1rem',
                    borderRadius: '12px',
                    background: 'rgba(3, 1, 6, 0.8)',
                    border: '1px solid var(--glass-border)',
                    boxShadow: 'var(--skeuo-shadow-inset)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.4rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.9rem', fontWeight: 800, color: '#ffffff' }}>
                      {c.message}
                    </span>
                    <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: '#c084fc', background: 'rgba(168,85,247,0.2)', padding: '0.15rem 0.5rem', borderRadius: '6px', fontWeight: 700 }}>
                      {c.commit_hash.slice(0, 7)}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    <span>Author: <strong style={{ color: 'var(--text-main)' }}>{c.author_name}</strong></span>
                    <span>Branch: <code style={{ color: '#c084fc' }}>{c.branch_name}</code></span>
                    <span>Timestamp: {new Date(c.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Push Authorization Modal */}
      {showPushModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(3, 7, 18, 0.85)', backdropFilter: 'blur(16px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="glass-panel" style={{ width: '100%', maxWidth: '520px', padding: '2.25rem', border: '1px solid rgba(255, 255, 255, 0.25)', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.9)' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#ffffff', marginBottom: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <UploadCloud size={24} color="#c084fc" /> Authorize Remote Git Push
            </h3>

            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '1.35rem', lineHeight: '1.55' }}>
              The agent is strictly forbidden from pushing to remote repositories automatically. To publish your committed branch <code style={{ color: '#c084fc' }}>{gitState.branch_name}</code>, confirm explicit authorization below.
            </p>

            {pushStatusMessage ? (
              <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.2)', border: '1px solid rgba(52, 211, 153, 0.4)', borderRadius: '12px', color: '#34d399', fontSize: '0.9rem', fontWeight: 700 }}>
                {pushStatusMessage}
              </div>
            ) : (
              <form onSubmit={handleConfirmPush} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase' }}>
                    Target Remote Repository
                  </label>
                  <input
                    type="text"
                    value={pushRemote}
                    onChange={(e) => setPushRemote(e.target.value)}
                    placeholder="origin"
                    required
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', background: 'rgba(3,1,6,0.8)', padding: '1rem', borderRadius: '12px', border: '1px solid var(--glass-border)' }}>
                  <input
                    type="checkbox"
                    id="confirmPush"
                    checked={confirmPushChecked}
                    onChange={(e) => setConfirmPushChecked(e.target.checked)}
                    style={{ width: '20px', height: '20px', cursor: 'pointer', accentColor: '#a855f7' }}
                  />
                  <label htmlFor="confirmPush" style={{ fontSize: '0.88rem', color: '#ffffff', fontWeight: 700, cursor: 'pointer' }}>
                    I explicitly authorize pushing branch '{gitState.branch_name}' to remote '{pushRemote}'
                  </label>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.85rem', marginTop: '0.6rem' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowPushModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn"
                    disabled={!confirmPushChecked}
                    style={{ opacity: confirmPushChecked ? 1 : 0.45 }}
                  >
                    Execute Remote Push
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
