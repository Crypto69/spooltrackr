<script setup>
defineProps({ title: String })
const emit = defineEmits(['close'])
</script>
<template>
  <div class="modal-back" @click.self="emit('close')">
    <div class="modal" role="dialog" :aria-label="title">
      <h3 v-if="title">{{ title }}</h3>
      <slot />
    </div>
  </div>
</template>
