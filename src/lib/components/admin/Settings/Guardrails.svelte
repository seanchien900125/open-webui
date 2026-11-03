<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import {
		getGuardrailsConfig,
		setGuardrailsConfig,
		testGuardrails,
		type GuardrailsTestResult
	} from '$lib/apis/guardrails';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import AdminSettingRow from './AdminSettingRow.svelte';

	const i18n = getContext('i18n');

	const PII_ACTIONS = ['off', 'log', 'mask', 'block'];
	const INJECTION_ACTIONS = ['off', 'log', 'block'];
	const PII_KINDS = ['email', 'phone', 'tw_id', 'credit_card', 'secret', 'ip_address'];

	let loading = true;
	let saving = false;
	let testing = false;
	let enabled = false;
	let piiAction = 'mask';
	let piiKinds: string[] = [];
	let injectionAction = 'log';
	let exemptAdmins = false;

	let sample = '';
	// Cleared whenever a setting or the sample changes so an old verdict is never shown.
	let result: GuardrailsTestResult | null = null;
	$: (enabled, piiAction, piiKinds, injectionAction, sample, (result = null));

	const apply = (config) => {
		enabled = config?.ENABLE_GUARDRAILS ?? false;
		piiAction = config?.GUARDRAILS_PII_ACTION ?? 'mask';
		piiKinds = config?.GUARDRAILS_PII_KINDS ?? [];
		injectionAction = config?.GUARDRAILS_INJECTION_ACTION ?? 'log';
		exemptAdmins = config?.GUARDRAILS_EXEMPT_ADMINS ?? false;
	};

	onMount(async () => {
		try {
			apply(await getGuardrailsConfig(localStorage.token));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			loading = false;
		}
	});

	const toggleKind = (kind: string) => {
		piiKinds = piiKinds.includes(kind) ? piiKinds.filter((k) => k !== kind) : [...piiKinds, kind];
	};

	const currentConfig = () => ({
		ENABLE_GUARDRAILS: enabled,
		GUARDRAILS_PII_ACTION: piiAction,
		GUARDRAILS_PII_KINDS: piiKinds,
		GUARDRAILS_INJECTION_ACTION: injectionAction,
		GUARDRAILS_EXEMPT_ADMINS: exemptAdmins
	});

	const save = async () => {
		saving = true;
		try {
			apply(await setGuardrailsConfig(localStorage.token, currentConfig()));
			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			saving = false;
		}
	};

	// The test runs against what is saved, so save first when the form has unsaved changes.
	const runTest = async () => {
		testing = true;
		try {
			await setGuardrailsConfig(localStorage.token, currentConfig());
			const outcome = await testGuardrails(localStorage.token, sample);
			result = outcome;
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			testing = false;
		}
	};

	const selectClass =
		'h-7 rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 text-xs text-gray-700 outline-hidden transition-colors focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300 dark:focus:border-blue-500';
</script>

<form class="flex h-full flex-col justify-between text-sm" on:submit|preventDefault={save}>
	<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">
		{$i18n.t('settings.admin.guardrails.title')}
	</h2>

	<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hover pr-1.5">
		{#if loading}
			<div class="flex justify-center py-8"><Spinner className="size-6" /></div>
		{:else}
			<div class="flex flex-col gap-2.5">
				<AdminSettingRow let:labelId>
					<span slot="label">{$i18n.t('settings.admin.guardrails.enable.label')}</span>
					<Switch ariaLabelledbyId={labelId} bind:state={enabled} />
				</AdminSettingRow>
				<p class="-mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t('settings.admin.guardrails.enable.description')}
				</p>

				<div>
					<label class="text-xs text-gray-600 dark:text-gray-400" for="gr-pii-action">
						{$i18n.t('settings.admin.guardrails.pii.action.label')}
					</label>
					<div class="mt-1">
						<select id="gr-pii-action" bind:value={piiAction} class={selectClass}>
							{#each PII_ACTIONS as action}
								<option value={action}>
									{$i18n.t(`settings.admin.guardrails.action.${action}`)}
								</option>
							{/each}
						</select>
					</div>
					<p class="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t('settings.admin.guardrails.pii.action.description')}
					</p>
				</div>

				<div>
					<div class="text-xs text-gray-600 dark:text-gray-400">
						{$i18n.t('settings.admin.guardrails.pii.kinds.label')}
					</div>
					<div class="mt-1 flex flex-wrap gap-x-4 gap-y-1.5">
						{#each PII_KINDS as kind}
							<label class="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300">
								<input
									type="checkbox"
									checked={piiKinds.includes(kind)}
									on:change={() => toggleKind(kind)}
								/>
								{$i18n.t(`settings.admin.guardrails.kind.${kind}`)}
							</label>
						{/each}
					</div>
				</div>

				<div>
					<label class="text-xs text-gray-600 dark:text-gray-400" for="gr-injection-action">
						{$i18n.t('settings.admin.guardrails.injection.action.label')}
					</label>
					<div class="mt-1">
						<select id="gr-injection-action" bind:value={injectionAction} class={selectClass}>
							{#each INJECTION_ACTIONS as action}
								<option value={action}>
									{$i18n.t(`settings.admin.guardrails.action.${action}`)}
								</option>
							{/each}
						</select>
					</div>
					<p class="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t('settings.admin.guardrails.injection.action.description')}
					</p>
				</div>

				<AdminSettingRow let:labelId>
					<span slot="label">{$i18n.t('settings.admin.guardrails.exemptAdmins.label')}</span>
					<Switch ariaLabelledbyId={labelId} bind:state={exemptAdmins} />
				</AdminSettingRow>

				<div
					class="rounded-lg border border-gray-100/50 bg-gray-50/40 p-2.5 dark:border-white/[0.04] dark:bg-white/[0.03]"
				>
					<div class="text-xs font-medium text-gray-900 dark:text-white">
						{$i18n.t('settings.admin.guardrails.test.title')}
					</div>
					<textarea
						class="mt-1.5 w-full rounded-lg border border-gray-100/50 bg-white/60 p-2 text-xs text-gray-700 outline-hidden focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.02] dark:text-gray-300 dark:focus:border-blue-500"
						rows="3"
						maxlength="20000"
						placeholder={$i18n.t('settings.admin.guardrails.test.placeholder')}
						bind:value={sample}
					></textarea>
					<div class="mt-1.5 flex items-center gap-2">
						<button
							type="button"
							class="flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-gray-200 px-2.5 text-xs text-gray-700 transition hover:bg-gray-100 disabled:opacity-60 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/5"
							disabled={testing || sample.trim() === ''}
							on:click={runTest}
						>
							{#if testing}<Spinner className="size-3" />{/if}
							{$i18n.t('settings.admin.guardrails.test.button')}
						</button>
						<span class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
							{$i18n.t('settings.admin.guardrails.test.description')}
						</span>
					</div>

					{#if result}
						<div class="mt-2 flex flex-col gap-1 text-xs">
							<div class="font-medium text-gray-900 dark:text-white">
								{$i18n.t(`settings.admin.guardrails.result.${result.action}`)}
							</div>
							{#each Object.entries(result.pii) as [kind, count]}
								<div class="text-gray-600 dark:text-gray-400">
									{$i18n.t(`settings.admin.guardrails.kind.${kind}`)} × {count}
								</div>
							{/each}
							{#each result.injection as category}
								<div class="text-gray-600 dark:text-gray-400">
									{$i18n.t(`settings.admin.guardrails.injection.category.${category}`)}
								</div>
							{/each}
							{#if result.action === 'masked'}
								<pre
									class="whitespace-pre-wrap break-words rounded-md bg-white/60 p-2 text-gray-700 dark:bg-white/[0.02] dark:text-gray-300">{result.text}</pre>
							{/if}
						</div>
					{/if}
				</div>

				<p class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t('settings.admin.guardrails.limits.description')}
				</p>
			</div>
		{/if}
	</div>

	{#if !loading}
		<div class="flex justify-end pt-6 text-sm font-normal">
			<button
				class="flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-gray-900 px-2.5 text-xs font-normal text-white transition hover:bg-black disabled:opacity-60 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white"
				type="submit"
				disabled={saving}
			>
				{$i18n.t('Save')}
			</button>
		</div>
	{/if}
</form>
