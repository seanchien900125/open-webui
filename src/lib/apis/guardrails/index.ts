import { WEBUI_API_BASE_URL } from '$lib/constants';

export type GuardrailsConfig = {
	ENABLE_GUARDRAILS: boolean;
	GUARDRAILS_PII_ACTION: 'off' | 'log' | 'mask' | 'block';
	GUARDRAILS_PII_KINDS: string[];
	GUARDRAILS_INJECTION_ACTION: 'off' | 'log' | 'block';
	GUARDRAILS_EXEMPT_ADMINS: boolean;
};

export type GuardrailsTestResult = {
	action: 'clean' | 'logged' | 'masked' | 'blocked';
	blocked_by: 'pii' | 'injection' | null;
	pii: Record<string, number>;
	injection: string[];
	text: string;
};

const request = async (token: string, path: string, method: string, body?: object) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/guardrails${path}`, {
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

export const getGuardrailsConfig = (token: string): Promise<GuardrailsConfig> =>
	request(token, '/config', 'GET');

export const setGuardrailsConfig = (
	token: string,
	config: Partial<GuardrailsConfig>
): Promise<GuardrailsConfig> => request(token, '/config', 'POST', config);

/** Runs a sample message through the saved settings. Nothing is stored or sent to a model. */
export const testGuardrails = (token: string, text: string): Promise<GuardrailsTestResult> =>
	request(token, '/test', 'POST', { text });
