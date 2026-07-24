/** @odoo-module **/

import { Component, onPatched, onWillStart, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { AccordionItem } from "@web/core/dropdown/accordion_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { user } from "@web/core/user";
import { ListController } from "@web/views/list/list_controller";
import { executeButtonCallback } from "@web/views/view_button/view_button_hook";

const favoriteMenuRegistry = registry.category("favoriteMenu");
let openCommentsPopup = null;
const COMMENT_USER_COLORS = [
    "#6F42C1",
    "#0D6EFD",
    "#198754",
    "#D63384",
    "#FD7E14",
    "#20C997",
];
const COMMENT_PREVIEW_LIMIT = 120;
const commentUserColorMap = new Map();

patch(ListController.prototype, {
    async onClickCreate() {
        if (this.props.resModel !== "advanced.filter") {
            return super.onClickCreate(...arguments);
        }
        const context = {
            ...(this.props.context || {}),
            default_relation_mode: "direct",
        };
        return executeButtonCallback(this.rootRef.el, () =>
            this.actionService.doAction({
                type: "ir.actions.act_window",
                name: _t("New Advanced Filter"),
                res_model: "advanced.filter",
                views: [[false, "form"]],
                view_mode: "form",
                target: "new",
                context,
            })
        );
    },
});

function getUserColor(userKey) {
    const key = String(userKey || "").trim().toLowerCase();
    if (!commentUserColorMap.has(key)) {
        const color = COMMENT_USER_COLORS[commentUserColorMap.size % COMMENT_USER_COLORS.length];
        commentUserColorMap.set(key, color);
    }
    return commentUserColorMap.get(key);
}

function getFirstName(fullName) {
    return String(fullName || "").trim().split(/\s+/)[0] || "";
}

export class AdvancedFilterFavoriteItem extends Component {
    static template = "advanced_filter_engine.AdvancedFilterFavoriteItem";
    static components = { AccordionItem };
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.notificationService = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            filters: [],
            isLoading: true,
            modelLabel: "",
        });

        onWillStart(async () => {
            await this.loadFilters();
        });
    }

    get resModel() {
        return this.env.searchModel?.resModel || false;
    }

    get hasFilters() {
        return this.state.filters.length > 0;
    }

    async loadFilters() {
        if (!this.resModel) {
            this.state.isLoading = false;
            return;
        }
        this.state.isLoading = true;
        try {
            const [filters, modelInfo] = await Promise.all([
                this.orm.call("advanced.filter", "get_filters_for_model", [this.resModel]),
                this.orm.searchRead(
                    "ir.model",
                    [["model", "=", this.resModel]],
                    ["name"],
                    { limit: 1 }
                ),
            ]);
            this.state.filters = filters;
            this.state.modelLabel = modelInfo[0]?.name || this.resModel;
        } catch {
            this.state.filters = [];
            this.state.modelLabel = this.resModel;
        } finally {
            this.state.isLoading = false;
        }
    }

    async applyFilter(filter) {
        try {
            const action = await this.orm.call("advanced.filter", "action_apply_filter", [[filter.id]]);
            await this.actionService.doAction(action);
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter could not be applied."),
                { type: "danger" }
            );
        }
    }

    async editFilter(filter) {
        try {
            const action = await this.orm.call("advanced.filter", "action_open_filter_form", [[filter.id]]);
            await this.actionService.doAction(action, {
                onClose: async () => this.loadFilters(),
            });
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter form could not be opened."),
                { type: "danger" }
            );
        }
    }

    async deleteFilter(filter) {
        if (!filter.is_owner) {
            return;
        }
        try {
            const result = await this.orm.call("advanced.filter", "delete_filter", [filter.id]);
            if (result?.error) {
                this.notificationService.add(result.error, { type: "danger" });
                return;
            }
            await this.loadFilters();
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter could not be deleted."),
                { type: "danger" }
            );
        }
    }

    async createFilter() {
        if (!this.resModel) {
            return;
        }
        try {
            const action = await this.orm.call("advanced.filter", "action_create_for_model", [this.resModel]);
            await this.actionService.doAction(action);
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter form could not be opened."),
                { type: "danger" }
            );
        }
    }

    async openManager() {
        await this.actionService.doAction("advanced_filter_engine.action_advanced_filter", {
            additionalContext: {
                search_default_my_filters: 1,
            },
        });
    }
}

favoriteMenuRegistry.add(
    "advanced-filter-favorite-item",
    {
        Component: AdvancedFilterFavoriteItem,
        groupNumber: 2,
        isDisplayed: (env) => Boolean(env.searchModel?.resModel && env.searchModel?.searchViewFields),
    },
    { sequence: 20 }
);

export class AdvancedFilterCommentsField extends Component {
    static template = "advanced_filter_engine.AdvancedFilterCommentsField";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.notificationService = useService("notification");
        this.newCommentRef = useRef("newComment");
        this.iconRef = useRef("commentIcon");
        this.onDocumentClick = () => {
            if (this.state.isPopupOpen) {
                this.closePopup();
            }
        };
        this.state = useState({
            comments: [],
            isLoading: true,
            isSending: false,
            draft: "",
            isPopupOpen: false,
            popupStyle: "",
            editingCommentId: false,
            editCommentValue: "",
            activeCommentId: false,
            hoveredCommentId: false,
            expandedCommentIds: {},
        });

        onWillStart(async () => {
            await this.loadComments();
        });

        document.addEventListener("click", this.onDocumentClick);

        onWillUnmount(() => {
            document.removeEventListener("click", this.onDocumentClick);
            if (openCommentsPopup === this) {
                openCommentsPopup = null;
            }
        });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.record.resId !== this.props.record.resId) {
                this.state.comments = [];
                this.state.draft = "";
                this.state.isPopupOpen = false;
                this.state.popupStyle = "";
                this.state.editingCommentId = false;
                this.state.editCommentValue = "";
                this.state.activeCommentId = false;
                this.state.hoveredCommentId = false;
                this.state.expandedCommentIds = {};
                await this.loadComments(nextProps.record.resId);
            }
        });

        onPatched(() => {
            if (this.state.isPopupOpen && this.newCommentRef.el) {
                this.resizeTextarea(this.newCommentRef.el);
            }
            if (!this.shouldFocusInlineEdit) {
                return;
            }
            const inlineInput = document.querySelector(
                `.o_afe_comment_inline_input[data-comment-id="${this.state.editingCommentId}"]`
            );
            if (inlineInput && document.activeElement !== inlineInput) {
                inlineInput.focus();
                inlineInput.select();
            }
            this.shouldFocusInlineEdit = false;
        });
    }

    get filterId() {
        return this.props.record.resId;
    }

    get commentRecordId() {
        return this.filterId;
    }

    get commentModel() {
        return "advanced.filter.comment";
    }

    get loadCommentsMethod() {
        return "get_comments_by_filter";
    }

    get addCommentMethod() {
        return "add_comment";
    }

    get updateCommentMethod() {
        return "update_comment";
    }

    get deleteCommentMethod() {
        return "delete_comment";
    }

    async loadComments(recordId = this.commentRecordId) {
        if (!recordId) {
            this.state.isLoading = false;
            return;
        }
        this.state.isLoading = true;
        try {
            this.state.comments = await this.orm.call(
                this.commentModel,
                this.loadCommentsMethod,
                [recordId]
            );
        } catch (error) {
            this.state.comments = [];
            this.notificationService.add(
                error.message || _t("Comments could not be loaded."),
                { type: "danger" }
            );
        } finally {
            this.state.isLoading = false;
        }
    }

    onDraftInput(event) {
        this.state.draft = event.target.value;
        this.resizeTextarea(event.target);
    }

    onPopupInput(event) {
        this.onDraftInput(event);
    }

    resizeTextarea(textarea) {
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(textarea.scrollHeight, 92)}px`;
    }

    stopPropagation() {}

    commentUserColor(comment) {
        if (comment.message_color) {
            return comment.message_color;
        }
        return getUserColor(comment.user_id || comment.username);
    }

    commentUserStyle(comment) {
        const color = this.commentUserColor(comment);
        return `color: ${color} !important;`;
    }

    commentDisplayName(comment) {
        return getFirstName(comment.username);
    }

    isCommentEditable(comment) {
        if (!comment) {
            return false;
        }
        if ("can_edit" in comment) {
            return Boolean(comment.can_edit);
        }
        if ("is_owner" in comment) {
            return Boolean(comment.is_owner);
        }
        return Number(comment.user_id) === Number(user.userId);
    }

    isEditingComment(comment) {
        return this.state.editingCommentId === comment.id;
    }

    isActiveComment(comment) {
        return this.state.activeCommentId === comment.id || this.state.hoveredCommentId === comment.id;
    }

    isCommentLong(comment) {
        return String(comment?.comment || "").length > COMMENT_PREVIEW_LIMIT;
    }

    isCommentExpanded(comment) {
        return Boolean(this.state.expandedCommentIds[comment.id]);
    }

    commentBodyText(comment) {
        const body = String(comment?.comment || "");
        if (!this.isCommentLong(comment) || this.isCommentExpanded(comment)) {
            return body;
        }
        return `${body.slice(0, COMMENT_PREVIEW_LIMIT).trimEnd()}...`;
    }

    toggleCommentExpanded(comment) {
        this.state.expandedCommentIds = {
            ...this.state.expandedCommentIds,
            [comment.id]: !this.isCommentExpanded(comment),
        };
    }

    commentItemClass(comment) {
        const classes = ["o_afe_comment_item"];
        if (this.isCommentEditable(comment)) {
            classes.push("o_afe_comment_item_editable");
        }
        if (this.isEditingComment(comment)) {
            classes.push("o_afe_comment_item_editing");
        }
        if (this.isActiveComment(comment)) {
            classes.push("o_afe_comment_item_active");
        }
        return classes.join(" ");
    }

    commentColumnClass() {
        return `o_afe_comment_column${this.state.isPopupOpen ? " o_afe_comment_popup_open" : ""}`;
    }

    onCommentMouseEnter(comment) {
        this.state.hoveredCommentId = comment.id;
    }

    onCommentMouseLeave(comment) {
        if (this.state.hoveredCommentId === comment.id) {
            this.state.hoveredCommentId = false;
        }
    }

    updatePopupPosition() {
        const icon = this.iconRef.el;
        if (!icon) {
            this.state.popupStyle = "";
            return;
        }
        const rect = icon.getBoundingClientRect();
        const popupWidth = Math.min(390, window.innerWidth - 16);
        const popupHeight = 300;
        const rightSpace = window.innerWidth - rect.right;
        const left = rightSpace >= popupWidth
            ? Math.min(rect.right + 6, window.innerWidth - popupWidth - 8)
            : Math.max(8, Math.min(rect.right - popupWidth, window.innerWidth - popupWidth - 8));
        let top = rect.bottom + 6;
        if (top + popupHeight > window.innerHeight - 8) {
            top = Math.max(8, rect.top - popupHeight - 6);
        }
        this.state.popupStyle = `left: ${left}px; top: ${top}px; width: ${popupWidth}px; max-height: ${popupHeight}px;`;
    }

    compactDate(comment) {
        const dateValue = comment.display_date || comment.created_at || "";
        const match = dateValue.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (!match) {
            return dateValue;
        }
        const [, year, month, day] = match;
        return `${Number(month)}/${Number(day)}/${year.slice(-2)}`;
    }

    openComposer() {
        if (this.state.isPopupOpen) {
            this.closePopup();
            return;
        }
        if (openCommentsPopup && openCommentsPopup !== this) {
            openCommentsPopup.closePopup();
        }
        openCommentsPopup = this;
        this.state.isPopupOpen = true;
        this.state.draft = "";
        this.updatePopupPosition();
    }

    closePopup() {
        this.state.isPopupOpen = false;
        this.state.popupStyle = "";
        this.state.draft = "";
        if (openCommentsPopup === this) {
            openCommentsPopup = null;
        }
    }

    async sendComment() {
        const body = this.state.draft.trim();
        if (!this.commentRecordId || !body || this.state.isSending) {
            return;
        }
        this.state.isSending = true;
        try {
            const comment = await this.orm.call(
                this.commentModel,
                this.addCommentMethod,
                [this.commentRecordId, body]
            );
            if (comment?.error) {
                this.notificationService.add(comment.error, { type: "danger" });
                return;
            }
            await this.loadComments();
            this.state.draft = "";
            this.state.isPopupOpen = false;
            if (this.newCommentRef.el) {
                this.newCommentRef.el.value = "";
                this.newCommentRef.el.style.height = "";
            }
        } catch (error) {
            this.notificationService.add(
                error.message || _t("Comment could not be saved."),
                { type: "danger" }
            );
        } finally {
            this.state.isSending = false;
        }
    }

    onComposerKeydown(event) {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            this.savePopup();
        }
    }

    startCommentEdit(comment) {
        this.state.activeCommentId = comment.id;
        if (!this.isCommentEditable(comment)) {
            return;
        }
        this.state.editingCommentId = comment.id;
        this.state.editCommentValue = comment.comment || "";
        this.shouldFocusInlineEdit = true;
    }

    onCommentEditInput(event) {
        this.state.editCommentValue = event.target.value;
    }

    onCommentEditKeydown(event, comment) {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            this.saveCommentEdit(comment);
        } else if (event.key === "Escape") {
            event.preventDefault();
            this.cancelCommentEdit();
        }
    }

    cancelCommentEdit() {
        this.state.editingCommentId = false;
        this.state.editCommentValue = "";
    }

    async saveCommentEdit(comment) {
        const body = this.state.editCommentValue.trim();
        if (!comment || !this.isCommentEditable(comment) || !body) {
            return;
        }
        try {
            const updatedComment = await this.orm.call(
                this.commentModel,
                this.updateCommentMethod,
                [comment.id, body]
            );
            if (updatedComment?.error) {
                this.notificationService.add(updatedComment.error, { type: "danger" });
                return;
            }
            this.state.comments = this.state.comments.map((item) =>
                item.id === updatedComment.id ? updatedComment : item
            );
            this.cancelCommentEdit();
        } catch (error) {
            this.notificationService.add(
                error.message || _t("Comment could not be updated."),
                { type: "danger" }
            );
        }
    }

    async deleteComment(comment) {
        if (!comment || !this.isCommentEditable(comment)) {
            return;
        }
        if (!window.confirm(_t("Delete this comment?"))) {
            return;
        }
        try {
            const result = await this.orm.call(
                this.commentModel,
                this.deleteCommentMethod,
                [comment.id]
            );
            if (result?.error) {
                this.notificationService.add(result.error, { type: "danger" });
                return;
            }
            this.state.comments = this.state.comments.filter((item) => item.id !== comment.id);
            if (this.state.editingCommentId === comment.id) {
                this.cancelCommentEdit();
            }
            if (this.state.activeCommentId === comment.id) {
                this.state.activeCommentId = false;
            }
            if (this.state.hoveredCommentId === comment.id) {
                this.state.hoveredCommentId = false;
            }
            if (this.state.expandedCommentIds[comment.id]) {
                const expandedCommentIds = { ...this.state.expandedCommentIds };
                delete expandedCommentIds[comment.id];
                this.state.expandedCommentIds = expandedCommentIds;
            }
        } catch (error) {
            this.notificationService.add(
                error.message || _t("Comment could not be deleted."),
                { type: "danger" }
            );
        }
    }

    savePopup() {
        return this.sendComment();
    }
}

registry.category("fields").add("advanced_filter_comments", {
    component: AdvancedFilterCommentsField,
    supportedTypes: ["char", "text"],
});

document.addEventListener("keydown", (event) => {
    if (event.target.closest?.(".o_afe_comment_column")) {
        return;
    }
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
        return;
    }

    const input = event.target.closest?.(
        ".o_afe_chat_composer input, .o_afe_chat_composer textarea, td[name='draft_comment'] input, td[name='draft_comment'] textarea"
    );
    if (!input || !input.value.trim()) {
        return;
    }

    event.preventDefault();
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.blur();
});
