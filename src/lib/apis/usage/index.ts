import { WEBUI_API_BASE_URL } from '$lib/constants';

export type UsageQuotaConfig = {
	ENABLE_USAGE_QUOTA: boolean;
	USAGE_QUOTA_DAILY_TOKENS: number;
	USAGE_QUOTA_MONTHLY_TOKENS: number;
	USAGE_QUOTA_EXEMPT_ADMINS: boolean;
};

export type UsageQuotaWindow = { limit: number; used: number; resets_at: number };

export type UsageQuotaStatus = {
	enabled: boolean;
	windows?: { daily?: UsageQuotaWindow; monthly?: UsageQuotaWindow };
};

const request = async (token: string, path: string, method: string, body?: object) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/usage${path}`, {
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

export const getUsageQuotaConfig = (token: string): Promise<UsageQuotaConfig> =>
	request(token, '/quota/config', 'GET');

export const setUsageQuotaConfig = (
	token: string,
	config: Partial<UsageQuotaConfig>
): Promise<UsageQuotaConfig> => request(token, '/quota/config', 'POST', config);

export const getMyUsageQuota = (token: string): Promise<UsageQuotaStatus> =>
	request(token, '/quota', 'GET');
