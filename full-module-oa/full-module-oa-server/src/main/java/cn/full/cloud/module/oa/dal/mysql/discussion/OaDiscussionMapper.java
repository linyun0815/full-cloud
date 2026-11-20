package cn.full.cloud.module.oa.dal.mysql.discussion;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.oa.controller.admin.discussion.vo.discussion.OaDiscussionPageReqVO;
import cn.full.cloud.module.oa.dal.dataobject.discussion.OaDiscussionDO;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import org.apache.ibatis.annotations.Mapper;

/**
 * OA 讨论 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface OaDiscussionMapper extends BaseMapperX<OaDiscussionDO> {

    default PageResult<OaDiscussionDO> selectPage(OaDiscussionPageReqVO pageReqVO) {
        return selectPage(pageReqVO, new LambdaQueryWrapperX<OaDiscussionDO>()
                .likeIfPresent(OaDiscussionDO::getTitle, pageReqVO.getTitle())
                .eqIfPresent(OaDiscussionDO::getType, pageReqVO.getType())
                .eqIfPresent(OaDiscussionDO::getUserId, pageReqVO.getUserId())
                .betweenIfPresent(OaDiscussionDO::getCreateTime, pageReqVO.getCreateTime())
                .orderByDesc(OaDiscussionDO::getId));
    }

    default void updateVisitCount(Long id) {
        update(new LambdaUpdateWrapper<OaDiscussionDO>().eq(OaDiscussionDO::getId, id)
                .setIncrBy(OaDiscussionDO::getVisitCount, 1));
    }

}
