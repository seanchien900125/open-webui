<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import {
		getChatRetentionConfig,
		previewChatRetention,
		setChatRetentionConfig
	} from '$lib/apis/retention';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import AdminSettingRow from './AdminSettingRow.svelte';

	const i18n = getContext('i18n');

	let loading = true;
	let saving = false;
	let previewing = false;
	let enabled = false;
	let days = 0;
	let keepPinned = true;
	let keepArchived = false;
	// null until the admin asks; reset whenever a setting changes so a stale number is never shown.
	let previewCount: number | null = null;

	// An emptied number input is bound as null; both it and a negative value mean "keep forever".
	const toDays = (value: number | null) => Math.max(0, Math.floor(Number(value) || 0));

	$: (days, keepPinned, keepArchived, (previewCount = null));

	onMount(async () => {
		try {
			const config = await getChatRetentionConfig(localStorage.token);
			enabled = config?.ENABLE_CHAT_RETENTION ?? false;
			days = toDays(config?.CHAT_RETENTION_DAYS);
			keepPinned = config?.CHAT_RETENTION_KEEP_PINNED ?? true;
			keepArchived = config?.CHAT_RETENTION_KEEP_ARCHIVED ?? false;
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			loading = false;
		}
	});

	const preview = async () => {
		previewing = true;
		try {
			const result = await previewChatRetention(
				localStorage.token,
				toDays(days),
				keepPinned,
				keepArchived
			);
			previewCount = result.count;
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			previewing = false;
		}
	};

	const save = async () => {
		saving = true;
		try {
			const config = await setChatRetentionConfig(localStorage.token, {
				ENABLE_CHAT_RETENTION: enabled,
				CHAT_RETENTION_DAYS: toDays(days),
				CHAT_RETENTION_KEEP_PINNED: keepPinned,
				CHAT_RETENTION_KEEP_ARCHIVED: keepArchived
			});
			days = toDays(config.CHAT_RETENTION_DAYS);
			toast.success($i18n.t('Settings saved successfully!'));
		} catch (error) {
			toast.error(`${error?.detail ?? error}`);
		} finally {
			saving = false;
		}
	};

	const inputClass =
		'h-7 w-24 rounded-lg border border-gray-100/50 bg-gray-50/40 px-2 text-xs text-gray-700 outline-hidden transition-colors focus:border-blue-400 dark:border-white/[0.04] dark:bg-white/[0.03] dark:text-gray-300 dark:focus:border-blue-500';
</script>

<form class="flex h-full flex-col justify-between text-sm" on:submit|preventDefault={save}>
	<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">
		{$i18n.t('settings.admin.retention.title')}
	</h2>

	<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hover pr-1.5">
		{#if loading}
			<div class="flex justify-center py-8"><Spinner className="size-6" /></div>
		{:else}
			<div class="flex flex-col gap-2.5">
				<AdminSettingRow let:labelId>
					<span slot="label">{$i18n.t('settings.admin.retention.enable.label')}</span>
					<Switch ariaLabelledbyId={labelId} bind:state={enabled} />
				</AdminSettingRow>
				<p class="-mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t('settings.admin.retention.enable.description')}
				</p>

				<div>
					<label class="text-xs text-gray-600 dark:text-gray-400" for="rt-days">
						{$i18n.t('settings.admin.retention.days.label')}
					</label>
					<div class="mt-1 flex items-center gap-1.5">
						<input id="rt-days" type="number" min="0" bind:value={days} class={inputClass} />
						<span class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
							{$i18n.t('settings.admin.retention.days.unit')}
						</span>
					</div>
					<p class="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t('settings.admin.retention.days.description')}
					</p>
				</div>

				<AdminSettingRow let:labelId>
					<span slot="label">{$i18n.t('settings.admin.retention.keepPinned.label')}</span>
					<Switch ariaLabelledbyId={labelId} bind:state={keepPinned} />
				</AdminSettingRow>

				<AdminSettingRow let:labelId>
					<span slot="label">{$i18n.t('settings.admin.retention.keepArchived.label')}</span>
					<Switch ariaLabelledbyId={labelId} bind:state={keepArchived} />
				</AdminSettingRow>

				<div
					class="rounded-lg border border-gray-100/50 bg-gray-50/40 p-2.5 dark:border-white/[0.04] dark:bg-white/[0.03]"
				>
					<div class="flex items-center gap-2">
						<button
							type="button"
							class="flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-gray-200 px-2.5 text-xs text-gray-700 transition hover:bg-gray-100 disabled:opacity-60 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/5"
							disabled={previewing || toDays(days) === 0}
							on:click={preview}
						>
							{#if previewing}<Spinner className="size-3" />{/if}
							{$i18n.t('settings.admin.retention.preview.button')}
						</button>
						{#if previewCount !== null}
							<span class="text-xs font-medium text-gray-900 dark:text-white">
								{$i18n.t('settings.admin.retention.preview.result', { COUNT: previewCount })}
							</span>
						{/if}
					</div>
					<p class="mt-1.5 text-[0.6875rem] text-gray-400 dark:text-gray-600">
						{$i18n.t('settings.admin.retention.preview.description')}
					</p>
				</div>

				<p class="text-[0.6875rem] text-gray-400 dark:text-gray-600">
					{$i18n.t('settings.admin.retention.irreversible.description')}
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
