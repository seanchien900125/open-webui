<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { getUsageQuotaConfig, setUsageQuotaConfig } from '$lib/apis/usage';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import AdminSettingRow from './AdminSettingRow.svelte';

	const i18n = getContext('i18n');

	let loading = true;
	let saving = false;
	let enabled = false;
	let exemptAdmins = true;
	let dailyTokens = 0;
	let monthlyTokens = 0;

	// An emptied number input is bound as null; both it and a negative value mean "no limit".
	const toLimit = (value: number | null) => Math.max(0, Math.floor(Number(value) || 0));

	onMount(async () => {
		try {
			const config = await getUsageQuotaConfig(localStorage.token);
			enabled = config?.ENABLE_USAGE_QUOTA ?? false;
			exemptAdmins = config?.USAGE_QUOTA_EXEMPT_ADMINS ?? true;
			dailyTokens = toLimit(config?.USAGE_QUOTA_DAILY_TOKENS);
			monthlyTokens = toLimit(config?.USAGE_QUOTA_MONTHLY_TOKENS);
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			loading = false;
		}
	});

	const save = async () => {
		saving = true;
		try {
			const config = await setUsageQuotaConfig(localStorage.token, {
				ENABLE_USAGE_QUOTA: enabled,
				USAGE_QUOTA_EXEMPT_ADMINS: exemptAdmins,
				USAGE_QUOTA_DAILY_TOKENS: toLimit(dailyTokens),
				USAGE_QUOTA_MONTHLY_TOKENS: toLimit(monthlyTokens)
			});
			dailyTokens = toLimit(config.USAGE_QUOTA_DAILY_TOKENS);
			monthlyTokens = toLimit(config.USAGE_QUOTA_MONTHLY_TOKENS);
			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			saving = false;
		}
	};

	const inputClass =
		'h-7 w-32 rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 text-xs text-gray-700 outline-hidden transition-colors focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300 dark:focus:border-blue-500';
</script>

<form class="flex h-full flex-col justify-between text-sm" on:submit|preventDefault={save}>
	<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">
		{$i18n.t('settings.admin.usageQuota.title')}
	</h2>

	<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hover pr-1.5">
		{#if loading}
			<div class="flex justify-center py-8"><Spinner className="size-6" /></div>
		{:else}
			<div class="flex flex-col gap-2.5">
				<AdminSettingRow let:labelId>
					<span slot="label">{$i18n.t('settings.admin.usageQuota.enable.label')}</span>
					<Switch ariaLabelledbyId={labelId} bind:state={enabled} />
				</AdminSettingRow>
				<p class="-mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t('settings.admin.usageQuota.enable.description')}
				</p>

				{#if enabled}
					<div>
						<label class="text-xs text-gray-600 dark:text-gray-400" for="uq-daily">
							{$i18n.t('settings.admin.usageQuota.daily.label')}
						</label>
						<div class="mt-1 flex items-center gap-1.5">
							<input
								id="uq-daily"
								type="number"
								min="0"
								step="1000"
								bind:value={dailyTokens}
								class={inputClass}
							/>
							<span class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
								{$i18n.t('settings.admin.usageQuota.unit')}
							</span>
						</div>
					</div>

					<div>
						<label class="text-xs text-gray-600 dark:text-gray-400" for="uq-monthly">
							{$i18n.t('settings.admin.usageQuota.monthly.label')}
						</label>
						<div class="mt-1 flex items-center gap-1.5">
							<input
								id="uq-monthly"
								type="number"
								min="0"
								step="10000"
								bind:value={monthlyTokens}
								class={inputClass}
							/>
							<span class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
								{$i18n.t('settings.admin.usageQuota.unit')}
							</span>
						</div>
					</div>
					<p class="-mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t('settings.admin.usageQuota.limits.description')}
					</p>

					<div>
						<AdminSettingRow let:labelId>
							<span slot="label">{$i18n.t('settings.admin.usageQuota.exemptAdmins.label')}</span>
							<Switch ariaLabelledbyId={labelId} bind:state={exemptAdmins} />
						</AdminSettingRow>
						<p class="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
							{$i18n.t('settings.admin.usageQuota.exemptAdmins.description')}
						</p>
					</div>

					<p class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t('settings.admin.usageQuota.softLimit.description')}
					</p>
				{/if}
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
