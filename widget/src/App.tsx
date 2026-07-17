import { useEffect, useRef, type ReactNode } from 'react';
import { bootstrap } from './bootstrap';
import { useTheme } from './theme/useTheme';
import { useNewConversation, useConversation } from './state/conversation';
import { BlockActionsContext } from './blocks/context';
import { RenderBlock } from './blocks/RenderBlock';
import { GeneratingIndicator } from './blocks/GeneratingIndicator';
import { Header } from './shell/Header';
import { ComplianceFooter } from './shell/ComplianceFooter';
import { WidgetFrame } from './shell/WidgetFrame';
import { AppSheet } from './shell/AppSheet';
import { SupportEntry } from './entry/SupportEntry';
import { ReportsEntry } from './entry/ReportsEntry';
import { registerPageTools, actionableChips, type WebMcpBridge } from './webmcp';
import './styles/widget.css';

/**
 * Top-level widget. Bootstraps the SessionContext from the URL once, resolves
 * the theme, seeds the first turn, renders the conversation, and picks the
 * shell by platform (web floating frame vs. app WebView sheet). WebMCP page
 * tools register through the same Conversation dispatch the UI uses.
 */
export function App() {
  const boot = useRef(bootstrap()).current;
  const { session, themeParam } = boot;
  useTheme(themeParam);

  const conversation = useNewConversation(session);
  const snap = useConversation(conversation);

  useEffect(() => {
    void conversation.seed();
  }, [conversation]);

  useEffect(() => {
    const bridge: WebMcpBridge = {
      sendMessage: (t) => void conversation.send(t),
      tapChip: (a) => void conversation.act(a),
      actionableChips: () => actionableChips(conversation.getSnapshot().blocks),
      getState: () => {
        const s = conversation.getSnapshot();
        return {
          blocks: s.blocks.map((b) => ({ type: b.type, text: 'text' in b ? b.text : undefined })),
          chips: actionableChips(s.blocks).map((c) => ({ label: c.label })),
          state: s.state,
          turn_number: s.turnNumber,
          caps: s.caps,
          pending: s.pending,
        };
      },
    };
    return registerPageTools(bridge);
  }, [conversation]);

  const onSend = (text: string) => void conversation.send(text);
  const onStartOver = () => void conversation.reset();

  const body = (
    <div className="jini-widget">
      <Header clientId={session.user_id} onStartOver={onStartOver} />
      <div className="wg-body" data-testid="wg-body">
        {snap.blocks.map((block, i) => (
          <RenderBlock key={i} block={block} />
        ))}
        {snap.slow && <GeneratingIndicator />}
      </div>
      <div className="wg-foot">
        {session.entry_surface === 'reports' ? (
          <ReportsEntry onSend={onSend} disabled={snap.pending} />
        ) : (
          <SupportEntry onSend={onSend} disabled={snap.pending} />
        )}
        <ComplianceFooter />
      </div>
    </div>
  );

  const shell: ReactNode =
    session.platform === 'webview' ? (
      <AppSheet>{body}</AppSheet>
    ) : (
      <WidgetFrame messageCount={snap.blocks.length}>{body}</WidgetFrame>
    );

  return (
    <BlockActionsContext.Provider value={{ dispatch: (a) => void conversation.act(a) }}>
      {shell}
    </BlockActionsContext.Provider>
  );
}
