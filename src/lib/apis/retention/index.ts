import { WEBUI_API_BASE_URL } from '$lib/constants';

export type ChatRetentionConfig = {
	ENABLE_CHAT_RETENTION: boolean;
	CHAT_RETENTION_DAYS: number;
	CHAT_RETENTION_KEEP_PINNED: boolean;
	CHAT_RETENTION_KEEP_ARCHIVED: boolean;
};

const request = async (token: string, path: string, method: string, body?: object) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/retention${path}`, {
		method,
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: body ? JSON.stringify(body) : undefined
	});
	if (!res.ok) throw await res.json();
	return res.json();
};

export const getChatRetentionConfig = (token: string): Promise<ChatRetentionConfig> =>
	request(token, '/chats/config', 'GET');

export const setChatRetentionConfig = (
	token: string,
	config: Partial<ChatRetentionConfig>
): Promise<ChatRetentionConfig> => request(token, '/chats/config', 'POST', config);

/** How many chats the given settings would delete right now. Nothing is deleted. */
export const previewChatRetention = (
	token: string,
	days: number,
	keepPinned: boolean,
	keepArchived: boolean
): Promise<{ count: number }> =>
	request(
		token,
		`/chats/preview?days=${days}&keep_pinned=${keepPinned}&keep_archived=${keepArchived}`,
		'GET'
	);
